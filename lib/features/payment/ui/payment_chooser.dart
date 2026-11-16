import 'package:flutter/material.dart';

import '../../../app/theme.dart';
import '../../../core/money.dart';
import '../data/malaysia_payments.dart';

/// Payment channel picker with the FPX bank list and e-wallet choice.
/// No credential is entered here; the gateway screen handles approval.
class PaymentChooser extends StatelessWidget {
  const PaymentChooser({
    super.key,
    required this.channel,
    required this.providerId,
    required this.onChanged,
    this.amountSen,
  });

  final PaymentChannel? channel;
  final String? providerId;
  final void Function(PaymentChannel channel, String? providerId) onChanged;

  /// Order total; FPX is disabled outside its RM 1 to RM 30,000 limit.
  final int? amountSen;

  bool _fpxAllowed() =>
      amountSen == null || (amountSen! >= fpxMinSen && amountSen! <= fpxMaxSen);

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('How would you like to pay?',
            style: Theme.of(context).textTheme.headlineSmall),
        const SizedBox(height: 4),
        Text('All payments are processed in Malaysian Ringgit (MYR).',
            style: Theme.of(context).textTheme.bodySmall),
        const SizedBox(height: 16),
        for (final c in PaymentChannel.values) ...[
          _ChannelCard(
            channel: c,
            selected: channel == c,
            enabled: c != PaymentChannel.fpx || _fpxAllowed(),
            disabledNote: 'FPX accepts RM 1.00 to RM 30,000.00 per payment.',
            onTap: () => onChanged(c, channel == c ? providerId : null),
            child: c.needsProvider && channel == c
                ? _ProviderGrid(
                    providers: providersFor(c),
                    selectedId: providerId,
                    onPick: (id) => onChanged(c, id),
                  )
                : null,
          ),
          const SizedBox(height: 10),
        ],
        const SizedBox(height: 4),
        Row(children: [
          const Icon(Icons.lock_outline, size: 16, color: kSuccess),
          const SizedBox(width: 6),
          Expanded(
            child: Text(
                'Secured checkout. Card and banking details are never stored by SageMaker.',
                style: Theme.of(context).textTheme.bodySmall),
          ),
        ]),
      ],
    );
  }
}

class _ChannelCard extends StatelessWidget {
  const _ChannelCard({
    required this.channel,
    required this.selected,
    required this.enabled,
    required this.disabledNote,
    required this.onTap,
    this.child,
  });

  final PaymentChannel channel;
  final bool selected;
  final bool enabled;
  final String disabledNote;
  final VoidCallback onTap;
  final Widget? child;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return AnimatedContainer(
      duration: const Duration(milliseconds: 220),
      curve: Curves.easeOut,
      decoration: BoxDecoration(
        color: kCard,
        borderRadius: BorderRadius.circular(kRadiusLarge),
        border: Border.all(
            color: selected ? kPrimary : const Color(0xFFEDE6D9),
            width: selected ? 2 : 1),
        boxShadow: selected ? softShadow(0.12) : const [],
      ),
      child: Material(
        type: MaterialType.transparency,
        child: InkWell(
          key: Key('channel-${channel.name}'),
          borderRadius: BorderRadius.circular(kRadiusLarge),
          onTap: enabled ? onTap : null,
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: Column(children: [
              Row(children: [
                AnimatedContainer(
                  duration: const Duration(milliseconds: 220),
                  width: 46,
                  height: 46,
                  decoration: BoxDecoration(
                    gradient: selected ? kHeroGradient : null,
                    color: selected ? null : const Color(0xFFF3EEE4),
                    borderRadius: BorderRadius.circular(14),
                  ),
                  child: Icon(channel.icon,
                      color: selected ? Colors.white : kPrimary),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Opacity(
                    opacity: enabled ? 1 : 0.45,
                    child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(channel.label,
                              style: theme.textTheme.titleMedium),
                          const SizedBox(height: 2),
                          Text(enabled ? channel.subtitle : disabledNote,
                              style: theme.textTheme.bodySmall),
                        ]),
                  ),
                ),
                AnimatedSwitcher(
                  duration: const Duration(milliseconds: 200),
                  child: Icon(
                    selected ? Icons.check_circle : Icons.circle_outlined,
                    key: ValueKey(selected),
                    color: selected ? kPrimary : const Color(0xFFD9D1C3),
                  ),
                ),
              ]),
              AnimatedSize(
                duration: const Duration(milliseconds: 260),
                curve: Curves.easeOutCubic,
                child: child == null
                    ? const SizedBox(width: double.infinity)
                    : Padding(
                        padding: const EdgeInsets.only(top: 14), child: child),
              ),
            ]),
          ),
        ),
      ),
    );
  }
}

class _ProviderGrid extends StatelessWidget {
  const _ProviderGrid(
      {required this.providers,
      required this.selectedId,
      required this.onPick});
  final List<PaymentProvider> providers;
  final String? selectedId;
  final ValueChanged<String> onPick;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(builder: (context, box) {
      final columns = box.maxWidth > 420 ? 4 : 3;
      final w = (box.maxWidth - (columns - 1) * 8) / columns;
      return Wrap(spacing: 8, runSpacing: 8, children: [
        for (final p in providers)
          SizedBox(
            width: w,
            child: ProviderTile(
              provider: p,
              selected: p.id == selectedId,
              onTap: p.online ? () => onPick(p.id) : null,
            ),
          ),
      ]);
    });
  }
}

/// Bank or wallet tile with a coloured initials badge.
class ProviderTile extends StatelessWidget {
  const ProviderTile(
      {super.key, required this.provider, required this.selected, this.onTap});
  final PaymentProvider provider;
  final bool selected;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final offline = !provider.online;
    return Semantics(
      button: true,
      selected: selected,
      label: offline ? '${provider.name}, offline' : provider.name,
      child: InkWell(
        key: Key('provider-${provider.id}'),
        onTap: onTap,
        borderRadius: BorderRadius.circular(14),
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 180),
          padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 6),
          decoration: BoxDecoration(
            color: selected ? const Color(0xFFE8F0EB) : const Color(0xFFFAF6EF),
            borderRadius: BorderRadius.circular(14),
            border: Border.all(
                color: selected ? kPrimary : Colors.transparent, width: 1.6),
          ),
          child: Opacity(
            opacity: offline ? 0.4 : 1,
            child: Column(children: [
              ProviderBadge(provider: provider, size: 36),
              const SizedBox(height: 6),
              Text(provider.name,
                  maxLines: 2,
                  textAlign: TextAlign.center,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                      fontSize: 11, fontWeight: FontWeight.w600, height: 1.2)),
              if (offline)
                const Text('Offline',
                    style: TextStyle(fontSize: 10, color: kMuted)),
            ]),
          ),
        ),
      ),
    );
  }
}

/// Round badge in the provider's colour with its initials.
class ProviderBadge extends StatelessWidget {
  const ProviderBadge({super.key, required this.provider, this.size = 40});
  final PaymentProvider provider;
  final double size;

  @override
  Widget build(BuildContext context) => Container(
        width: size,
        height: size,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: provider.color,
          borderRadius: BorderRadius.circular(size * 0.32),
        ),
        child: Text(provider.short,
            style: TextStyle(
                color: provider.onColor,
                fontWeight: FontWeight.w800,
                fontSize: size * (provider.short.length > 2 ? 0.28 : 0.36))),
      );
}

/// One-line summary used on the review step and order screens.
String paymentSummary(PaymentChannel? channel, String? providerId) {
  if (channel == null) return '';
  final p = providerById(providerId);
  return p == null || !channel.needsProvider
      ? channel.label
      : '${channel.label} · ${p.name}';
}

/// Formats an amount for gateway screens.
String gatewayAmount(int sen) => formatRm(sen);
