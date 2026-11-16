import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/money.dart';
import '../../../../core/network/app_failure.dart';
import '../../../../core/widgets/async_value_view.dart';
import '../../../../core/widgets/demo_label.dart';
import '../../../custom_orders/data/custom_order_models.dart';
import '../../products/data/admin_product_validation.dart';
import '../data/staff_custom_orders.dart';
import '../state/staff_custom_orders_provider.dart';

/// Staff custom-order list with status filter and actions: accept with a
/// price, reject with a reason, assign an artisan, advance status
/// (Req 25.1 to 25.10).
class StaffCustomOrdersScreen extends ConsumerWidget {
  const StaffCustomOrdersScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final filter = ref.watch(customOrderFilterProvider);
    final value = ref.watch(staffCustomOrdersProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Custom orders')),
      body: Column(children: [
        Padding(
          padding: const EdgeInsets.all(8),
          child: Wrap(spacing: 8, children: [
            ChoiceChip(
              key: const ValueKey('filter-all'),
              label: const Text('All'),
              selected: filter == null,
              onSelected: (_) =>
                  ref.read(customOrderFilterProvider.notifier).set(null),
            ),
            for (final s in customOrderStatuses)
              ChoiceChip(
                key: ValueKey('filter-$s'),
                label: Text(customOrderStatusLabel(s)),
                selected: filter == s,
                onSelected: (_) =>
                    ref.read(customOrderFilterProvider.notifier).set(s),
              ),
          ]),
        ),
        Expanded(
          child: AsyncValueView<StaffCustomOrderPage>(
            value: value,
            onRetry: () => ref.invalidate(staffCustomOrdersProvider),
            isEmpty: (p) => p.items.isEmpty,
            emptyMessage: filter == null
                ? 'No custom orders yet. Total: 0'
                : 'No custom orders with this status.',
            emptyActionLabel: filter == null ? 'Refresh' : 'Show all',
            onEmptyAction: () => filter == null
                ? ref.invalidate(staffCustomOrdersProvider)
                : ref.read(customOrderFilterProvider.notifier).set(null),
            errorMessage: (e) => e is AppFailure ? e.message : 'Server error',
            data: (page) => RefreshIndicator(
              onRefresh: () async => ref.invalidate(staffCustomOrdersProvider),
              child: ListView(children: [
                for (final o in page.items) _OrderCard(order: o),
                if (page.hasMore)
                  Padding(
                    padding: const EdgeInsets.all(12),
                    child: OutlinedButton(
                        onPressed: () => ref
                            .read(staffCustomOrdersProvider.notifier)
                            .loadMore(),
                        child: const Text('Load more')),
                  ),
              ]),
            ),
          ),
        ),
      ]),
    );
  }
}

class _OrderCard extends ConsumerWidget {
  const _OrderCard({required this.order});
  final StaffCustomOrder order;

  Future<void> _run(BuildContext context, WidgetRef ref,
      Future<void> Function() action) async {
    final messenger = ScaffoldMessenger.of(context);
    try {
      await action();
      ref.invalidate(staffCustomOrdersProvider);
    } on AppFailure catch (e) {
      messenger.showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final repo = ref.read(staffCustomOrdersRepositoryProvider);
    final o = order;
    final next = o.nextStatus;
    return Card(
      key: ValueKey('custom-order-${o.id}'),
      margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Expanded(
                child: Text('#${o.id} · ${o.productType}',
                    style: Theme.of(context).textTheme.titleMedium)),
            Chip(label: Text(customOrderStatusLabel(o.status))),
          ]),
          if (o.isDemo) const Align(alignment: Alignment.centerLeft, child: DemoLabel.item()),
          Text(o.description, maxLines: 3, overflow: TextOverflow.ellipsis),
          Text('Quantity ${o.quantity} · Preferred ${o.preferredDate}'),
          if (o.estimatedPriceSen != null)
            Text('Estimate ${formatRm(o.estimatedPriceSen!)}'),
          if (o.rejectReason != null) Text('Reason: ${o.rejectReason}'),
          if (o.productionLabel != null)
            Text('Production: ${o.productionLabel}'
                '${o.productionProgressPercent != null ? ' (${o.productionProgressPercent}%)' : ''}'),
          Wrap(spacing: 8, children: [
            if (o.canAccept)
              FilledButton(
                key: ValueKey('accept-${o.id}'),
                onPressed: () async {
                  final sen = await _askPrice(context);
                  if (sen != null && context.mounted) {
                    await _run(context, ref, () => repo.accept(o.id, sen));
                  }
                },
                child: const Text('Accept'),
              ),
            if (o.canReject)
              OutlinedButton(
                key: ValueKey('reject-${o.id}'),
                onPressed: () async {
                  final reason = await _askReason(context);
                  if (reason != null && context.mounted) {
                    await _run(context, ref, () => repo.reject(o.id, reason));
                  }
                },
                child: const Text('Reject'),
              ),
            if (o.canAssign)
              FilledButton.tonal(
                key: ValueKey('assign-${o.id}'),
                onPressed: () async {
                  final id = await showDialog<int>(
                      context: context,
                      builder: (_) => const _ArtisanPicker());
                  if (id != null && context.mounted) {
                    await _run(context, ref, () => repo.assign(o.id, id));
                  }
                },
                child: const Text('Assign artisan'),
              ),
            if (next != null)
              OutlinedButton(
                key: ValueKey('status-${o.id}'),
                onPressed: () =>
                    _run(context, ref, () => repo.setStatus(o.id, next)),
                child: Text('Mark ${customOrderStatusLabel(next).toLowerCase()}'),
              ),
          ]),
        ]),
      ),
    );
  }
}

Future<int?> _askPrice(BuildContext context) => showDialog<int>(
    context: context, builder: (_) => const _PriceDialog());

Future<String?> _askReason(BuildContext context) => showDialog<String>(
    context: context, builder: (_) => const _ReasonDialog());

class _PriceDialog extends StatefulWidget {
  const _PriceDialog();
  @override
  State<_PriceDialog> createState() => _PriceDialogState();
}

class _PriceDialogState extends State<_PriceDialog> {
  final _c = TextEditingController();
  String? _error;

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: const Text('Accept with estimated price'),
        content: TextField(
          controller: _c,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          decoration: InputDecoration(
              labelText: 'Estimated price (RM)', errorText: _error),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Cancel')),
          FilledButton(
            onPressed: () {
              final e = validatePriceRm(_c.text);
              if (e != null) return setState(() => _error = e);
              Navigator.pop(context, parsePriceSen(_c.text));
            },
            child: const Text('Accept'),
          ),
        ],
      );
}

class _ReasonDialog extends StatefulWidget {
  const _ReasonDialog();
  @override
  State<_ReasonDialog> createState() => _ReasonDialogState();
}

class _ReasonDialogState extends State<_ReasonDialog> {
  final _c = TextEditingController();
  String? _error;

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: const Text('Reject custom order'),
        content: TextField(
          controller: _c,
          maxLines: 3,
          decoration: InputDecoration(labelText: 'Reason', errorText: _error),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Cancel')),
          FilledButton(
            onPressed: () {
              final e = validateRejectReason(_c.text);
              if (e != null) return setState(() => _error = e);
              Navigator.pop(context, _c.text.trim());
            },
            child: const Text('Reject'),
          ),
        ],
      );
}

class _ArtisanPicker extends ConsumerWidget {
  const _ArtisanPicker();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final artisans = ref.watch(assignableArtisansProvider);
    return AlertDialog(
      title: const Text('Assign artisan'),
      content: SizedBox(
        width: 320,
        child: artisans.when(
          loading: () => const SizedBox(
              height: 80, child: Center(child: CircularProgressIndicator())),
          error: (e, _) => Text(e is AppFailure ? e.message : 'Server error'),
          data: (list) => list.isEmpty
              ? const Text('No active artisans.')
              : ListView(shrinkWrap: true, children: [
                  for (final a in list)
                    ListTile(
                      key: ValueKey('artisan-${a.id}'),
                      title: Text(a.name),
                      subtitle: Text(a.specialisation),
                      onTap: () => Navigator.pop(context, a.id),
                    ),
                ]),
        ),
      ),
      actions: [
        TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancel')),
      ],
    );
  }
}
