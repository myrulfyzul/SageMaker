import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../app/theme.dart';
import '../../../core/constants.dart';
import '../../../core/money.dart';
import '../../../core/widgets/empty_view.dart';
import '../../../core/widgets/error_view.dart';
import '../../../core/widgets/loading_view.dart';
import '../../../core/widgets/ui_kit.dart';
import '../../payment/data/malaysia_payments.dart';
import '../../payment/ui/payment_chooser.dart';
import '../../payment/ui/payment_gateway_screen.dart';
import '../data/checkout_models.dart';
import '../data/checkout_repository.dart';
import '../state/checkout_flow.dart';

/// Four-step checkout: cart review, delivery details, payment method,
/// confirmation (Req 12.1).
class CheckoutScreen extends ConsumerWidget {
  const CheckoutScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final flow = ref.watch(checkoutFlowProvider);
    final cart = ref.watch(checkoutCartProvider);
    final address = ref.watch(defaultAddressProvider);

    // Prefill once from the default address (Req 12.5). A failed address
    // lookup just leaves the form blank.
    if (!flow.prefilled && !address.isLoading) {
      final value = address.hasError ? null : address.value;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (context.mounted) {
          ref.read(checkoutFlowProvider.notifier).prefill(value);
        }
      });
    }

    return Scaffold(
      appBar: AppBar(title: const Text('Checkout')),
      body: cart.when(
        loading: () => const LoadingView(),
        error: (e, _) => ErrorView(
            message: 'Could not load your cart',
            onRetry: () => ref.invalidate(checkoutCartProvider)),
        data: (c) {
          if (c.isEmpty) {
            return EmptyView(
                message: 'Your cart is empty.',
                actionLabel: 'Browse products',
                onAction: () => context.go('/shop'));
          }
          return Column(children: [
            _StepHeader(step: flow.step),
            Expanded(
              child: ListView(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
                children: [
                  AnimatedSwitcher(
                    duration: const Duration(milliseconds: 280),
                    transitionBuilder: (child, a) => FadeTransition(
                      opacity: a,
                      child: SlideTransition(
                        position: Tween(
                                begin: const Offset(0.06, 0), end: Offset.zero)
                            .animate(a),
                        child: child,
                      ),
                    ),
                    child: KeyedSubtree(
                      key: ValueKey(flow.step),
                      child: switch (flow.step) {
                        0 => _CartReview(cart: c),
                        1 => _DeliveryStep(
                            key: ValueKey('delivery-${flow.formVersion}')),
                        2 => _PaymentStep(amountSen: c.grandTotalSen),
                        _ => _ConfirmStep(cart: c),
                      },
                    ),
                  ),
                ],
              ),
            ),
            _StepButtons(cart: c),
          ]);
        },
      ),
    );
  }
}

class _StepHeader extends StatelessWidget {
  const _StepHeader({required this.step});
  final int step;

  static const _icons = [
    Icons.shopping_bag_outlined,
    Icons.local_shipping_outlined,
    Icons.payments_outlined,
    Icons.fact_check_outlined,
  ];

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 4, 16, 8),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          for (var i = 0; i < 4; i++) ...[
            AnimatedContainer(
              duration: const Duration(milliseconds: 260),
              width: 38,
              height: 38,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                gradient: i <= step ? kHeroGradient : null,
                color: i <= step ? null : const Color(0xFFEDE6D9),
              ),
              child: Icon(i < step ? Icons.check : _icons[i],
                  size: 18, color: i <= step ? Colors.white : kMuted),
            ),
            if (i < 3)
              Expanded(
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 260),
                  height: 3,
                  margin: const EdgeInsets.symmetric(horizontal: 6),
                  decoration: BoxDecoration(
                    color: i < step ? kPrimary : const Color(0xFFEDE6D9),
                    borderRadius: BorderRadius.circular(9),
                  ),
                ),
              ),
          ],
        ]),
        const SizedBox(height: 10),
        Text('Step ${step + 1} of 4: ${checkoutStepTitles[step]}',
            key: const Key('stepTitle'),
            style: Theme.of(context).textTheme.titleMedium),
      ]),
    );
  }
}

class _StepButtons extends ConsumerWidget {
  const _StepButtons({required this.cart});
  final CheckoutCart cart;

  Future<void> _placeOrder(BuildContext context, WidgetRef ref) async {
    final notifier = ref.read(checkoutFlowProvider.notifier);
    final flow = ref.read(checkoutFlowProvider);
    final channel = flow.channel ??
        PaymentChannel.values.firstWhere((c) => c.method == flow.method,
            orElse: () => PaymentChannel.cod);
    if (channel != PaymentChannel.cod) {
      final outcome = await openPaymentGateway(context,
          channel: channel,
          providerId: flow.providerId,
          amountSen: cart.grandTotalSen);
      if (outcome == null) return; // closed without deciding: no order
      notifier.chooseOutcome(outcome);
    }
    final id = await notifier.submit();
    if (id != null && context.mounted) context.go('/confirmation/$id');
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final flow = ref.watch(checkoutFlowProvider);
    final notifier = ref.read(checkoutFlowProvider.notifier);
    final blocked = flow.step == 0 && cart.hasUnavailable;
    final isCod = flow.method == 'cod';
    return Container(
      decoration: BoxDecoration(
        color: kCard,
        boxShadow: softShadow(0.10),
        borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
      ),
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 14, 16, 12),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            if (flow.error != null)
              Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: Text(flow.error!,
                    key: const Key('checkoutError'),
                    style: const TextStyle(color: kError)),
              ),
            for (final s in flow.shortages) Text(s.text),
            Row(children: [
              const Text('Total', style: TextStyle(color: kMuted)),
              const Spacer(),
              Text(formatRm(cart.grandTotalSen),
                  style: Theme.of(context).textTheme.titleLarge),
            ]),
            const SizedBox(height: 10),
            Row(children: [
              if (flow.step > 0)
                Padding(
                  padding: const EdgeInsets.only(right: 8),
                  child: OutlinedButton(
                      onPressed: flow.submitting
                          ? null
                          : () => notifier.goTo(flow.step - 1),
                      child: const Text('Back')),
                ),
              Expanded(
                child: FilledButton(
                  key: const Key('stepNext'),
                  onPressed: blocked || flow.submitting
                      ? null
                      : () async {
                          switch (flow.step) {
                            case 0:
                              notifier.goTo(1);
                            case 1:
                              notifier.continueFromDelivery();
                            case 2:
                              notifier.continueFromPayment();
                            default:
                              await _placeOrder(context, ref);
                          }
                        },
                  child: Text(switch (flow.step) {
                    0 => 'Continue to delivery',
                    1 => 'Continue to payment',
                    2 => 'Review order',
                    _ => flow.submitting
                        ? 'Placing order...'
                        : isCod
                            ? 'Place order'
                            : 'Pay ${formatRm(cart.grandTotalSen)}',
                  }),
                ),
              ),
            ]),
          ]),
        ),
      ),
    );
  }
}

class _CartReview extends StatelessWidget {
  const _CartReview({required this.cart});
  final CheckoutCart cart;

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      for (final (i, l) in cart.lines.indexed)
        FadeSlideIn(
          index: i,
          child: Padding(
            padding: const EdgeInsets.only(bottom: 10),
            child: SoftCard(
              padding: const EdgeInsets.all(12),
              child: Row(children: [
                Container(
                  width: 44,
                  height: 44,
                  decoration: BoxDecoration(
                    color: const Color(0xFFF3EEE4),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  alignment: Alignment.center,
                  child: Text('${l.quantity}x',
                      style: const TextStyle(
                          fontWeight: FontWeight.w800, color: kPrimary)),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(l.name,
                            style: Theme.of(context).textTheme.titleSmall),
                        Text(
                            l.available
                                ? '${l.variationLabel ?? ''} Qty ${l.quantity}'
                                    .trim()
                                : 'No longer available. Remove it from your cart to continue.',
                            style: TextStyle(
                                fontSize: 12,
                                color: l.available ? kMuted : kError)),
                      ]),
                ),
                Text(formatRm(l.lineTotalSen),
                    style: const TextStyle(fontWeight: FontWeight.w700)),
              ]),
            ),
          ),
        ),
      const SizedBox(height: 6),
      SoftCard(child: _TotalLines(cart: cart)),
      if (cart.hasUnavailable)
        TextButton(
            onPressed: () => context.go('/cart'),
            child: const Text('Back to cart')),
    ]);
  }
}

class _TotalLines extends StatelessWidget {
  const _TotalLines({required this.cart});
  final CheckoutCart cart;

  Widget _row(String a, String b, {bool bold = false}) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 3),
        child: Row(children: [
          Expanded(
              child: Text(a,
                  style: TextStyle(
                      fontSize: bold ? 16 : 14,
                      color: bold ? kText : kMuted,
                      fontWeight: bold ? FontWeight.w800 : FontWeight.w500))),
          Text(b,
              style: TextStyle(
                  fontSize: bold ? 16 : 14,
                  fontWeight: bold ? FontWeight.w800 : FontWeight.w600)),
        ]),
      );

  @override
  Widget build(BuildContext context) => Column(children: [
        _row('Subtotal', formatRm(cart.subtotalSen)),
        _row('Delivery', formatRm(cart.deliveryFeeSen)),
        const Divider(height: 16),
        _row('Total', formatRm(cart.grandTotalSen), bold: true),
      ]);
}

class _DeliveryStep extends ConsumerStatefulWidget {
  const _DeliveryStep({super.key});

  @override
  ConsumerState<_DeliveryStep> createState() => _DeliveryStepState();
}

class _DeliveryStepState extends ConsumerState<_DeliveryStep> {
  late final Map<String, TextEditingController> _c;

  @override
  void initState() {
    super.initState();
    final f = ref.read(checkoutFlowProvider).delivery;
    _c = {
      'name': TextEditingController(text: f.name),
      'phone': TextEditingController(text: f.phone),
      'email': TextEditingController(text: f.email),
      'address': TextEditingController(text: f.address),
      'postcode': TextEditingController(text: f.postcode),
      'notes': TextEditingController(text: f.notes),
    };
  }

  @override
  void dispose() {
    for (final c in _c.values) {
      c.dispose();
    }
    super.dispose();
  }

  void _push({String? state}) {
    ref.read(checkoutFlowProvider.notifier).updateDelivery(DeliveryForm(
          name: _c['name']!.text,
          phone: _c['phone']!.text,
          email: _c['email']!.text,
          address: _c['address']!.text,
          postcode: _c['postcode']!.text,
          state: state ?? ref.read(checkoutFlowProvider).delivery.state,
          notes: _c['notes']!.text,
        ));
  }

  Widget _field(String key, String label,
      {TextInputType? type,
      int maxLines = 1,
      int? maxLength,
      IconData? icon,
      String? hint}) {
    final errors = ref.watch(checkoutFlowProvider.select((s) => s.errors));
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: TextField(
        key: Key('field-$key'),
        controller: _c[key],
        keyboardType: type,
        maxLines: maxLines,
        maxLength: maxLength,
        onChanged: (_) => _push(),
        decoration: InputDecoration(
          labelText: label,
          hintText: hint,
          errorText: errors[key],
          prefixIcon: icon == null ? null : Icon(icon),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final flow = ref.watch(checkoutFlowProvider);
    final stateValue = malaysianStates.contains(flow.delivery.state)
        ? flow.delivery.state
        : null;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text('Where should we deliver?',
          style: Theme.of(context).textTheme.headlineSmall),
      const SizedBox(height: 14),
      _field('name', 'Full name', icon: Icons.person_outline),
      _field('phone', 'Phone',
          type: TextInputType.phone,
          icon: Icons.phone_outlined,
          hint: '012-345 6789'),
      _field('email', 'Email',
          type: TextInputType.emailAddress, icon: Icons.mail_outline),
      _field('address', 'Address', maxLines: 3, icon: Icons.home_outlined),
      Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Expanded(
            child: _field('postcode', 'Postcode',
                type: TextInputType.number, hint: '50450')),
        const SizedBox(width: 10),
        Expanded(
          flex: 2,
          child: Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: DropdownButtonFormField<String>(
              key: Key('field-state-${flow.formVersion}'),
              initialValue: stateValue,
              isExpanded: true,
              decoration: InputDecoration(
                labelText: 'State',
                errorText: flow.errors['state'],
              ),
              items: [
                for (final s in malaysianStates)
                  DropdownMenuItem(value: s, child: Text(s)),
              ],
              onChanged: (v) => _push(state: v ?? ''),
            ),
          ),
        ),
      ]),
      _field('notes', 'Delivery notes (optional)', maxLines: 2, maxLength: 500),
    ]);
  }
}

class _PaymentStep extends ConsumerWidget {
  const _PaymentStep({required this.amountSen});
  final int amountSen;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final flow = ref.watch(checkoutFlowProvider);
    final notifier = ref.read(checkoutFlowProvider.notifier);
    return PaymentChooser(
      channel: flow.channel,
      providerId: flow.providerId,
      amountSen: amountSen,
      onChanged: (c, p) => notifier.chooseChannel(c, providerId: p),
    );
  }
}

class _ConfirmStep extends ConsumerWidget {
  const _ConfirmStep({required this.cart});
  final CheckoutCart cart;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final flow = ref.watch(checkoutFlowProvider);
    final d = flow.delivery;
    final method = flow.method;
    final theme = Theme.of(context);
    Widget section(IconData icon, String title, Widget body, int step) =>
        Padding(
          padding: const EdgeInsets.only(bottom: 12),
          child: SoftCard(
            child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Icon(icon, color: kPrimary),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(title, style: theme.textTheme.titleMedium),
                      const SizedBox(height: 4),
                      body,
                    ]),
              ),
              TextButton(
                  onPressed: () =>
                      ref.read(checkoutFlowProvider.notifier).goTo(step),
                  child: const Text('Edit')),
            ]),
          ),
        );
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text('Review your order', style: theme.textTheme.headlineSmall),
      const SizedBox(height: 14),
      section(
          Icons.location_on_outlined,
          'Deliver to',
          Text(
              '${d.name}\n${d.address}\n${d.postcode} ${d.state}\n${d.phone}\n${d.email}'
              '${d.notes.trim().isNotEmpty ? '\nNotes: ${d.notes.trim()}' : ''}'),
          1),
      section(
          Icons.payments_outlined,
          'Payment',
          Text(method == null
              ? ''
              : flow.channel != null
                  ? paymentSummary(flow.channel, flow.providerId)
                  : paymentMethodLabel(method)),
          2),
      SoftCard(child: _TotalLines(cart: cart)),
    ]);
  }
}
