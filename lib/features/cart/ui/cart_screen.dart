import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/money.dart';
import '../../../core/widgets/async_value_view.dart';
import '../../../core/widgets/total_row.dart';
import '../data/cart_models.dart';
import '../state/cart_provider.dart';

/// Cart tab: lines with server prices, unavailable flags, quantity controls,
/// totals, the not-merged notice and the empty state (Req 11, 18.4 to 18.6).
class CartScreen extends ConsumerWidget {
  const CartScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final value = ref.watch(cartProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Cart')),
      body: AsyncValueView<CartState>(
        value: value,
        onRetry: () => ref.read(cartProvider.notifier).retry(),
        isEmpty: (s) =>
            s.cart.lines.isEmpty && s.notMerged.isEmpty && !s.mergePending,
        emptyMessage: 'Your cart is empty.',
        emptyActionLabel: 'Explore products',
        onEmptyAction: () => context.go('/shop'),
        data: (s) => _CartBody(state: s),
      ),
    );
  }
}

class _CartBody extends ConsumerWidget {
  const _CartBody({required this.state});
  final CartState state;

  Future<void> _run(
      BuildContext context, Future<String?> Function() action) async {
    final messenger = ScaffoldMessenger.of(context);
    final error = await action();
    if (error != null) messenger.showSnackBar(SnackBar(content: Text(error)));
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final notifier = ref.read(cartProvider.notifier);
    final cart = state.cart;
    return Column(children: [
      if (state.mergePending)
        MaterialBanner(
          key: const Key('merge-pending'),
          content: const Text(
              'Your cart on this device could not be added to your account yet.'),
          actions: [
            TextButton(onPressed: notifier.retry, child: const Text('Retry')),
          ],
        ),
      if (state.notMerged.isNotEmpty)
        MaterialBanner(
          key: const Key('not-merged'),
          content: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('Some items from this device were not added:'),
              for (final n in state.notMerged)
                Text('${n.name ?? 'Product ${n.productId}'} '
                    'x${n.quantity}: ${n.reasonText}'),
            ],
          ),
          actions: [
            TextButton(
                onPressed: notifier.dismissNotMerged,
                child: const Text('Dismiss')),
          ],
        ),
      Expanded(
        child: ListView(children: [
          for (final line in cart.lines)
            _LineTile(
              line: line,
              onSet: (q) => _run(context, () => notifier.setQuantity(line, q)),
              onRemove: () => _run(context, () => notifier.remove(line)),
            ),
        ]),
      ),
      if (cart.lines.isNotEmpty)
        SafeArea(
          top: false,
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              TotalRow('Subtotal', formatRm(cart.subtotalSen)),
              TotalRow('Delivery', formatRm(cart.deliveryFeeSen)),
              const Divider(),
              TotalRow('Total', formatRm(cart.grandTotalSen), strong: true),
              const SizedBox(height: 12),
              SizedBox(
                width: double.infinity,
                child: FilledButton(
                  key: const Key('checkout'),
                  onPressed: cart.hasAvailableLines
                      ? () => context.push('/checkout')
                      : null,
                  child: const Text('Checkout'),
                ),
              ),
            ]),
          ),
        ),
    ]);
  }
}

class _LineTile extends StatelessWidget {
  const _LineTile(
      {required this.line, required this.onSet, required this.onRemove});
  final CartLine line;
  final void Function(int quantity) onSet;
  final VoidCallback onRemove;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final title = line.name ?? 'Product ${line.productId}';
    return ListTile(
      key: ValueKey('cart-line-${line.key}'),
      title: Text(line.variationLabel == null
          ? title
          : '$title (${line.variationLabel})'),
      subtitle: line.available
          ? Text('${formatRm(line.unitPriceSen)} each, '
              '${formatRm(line.lineTotalSen)}')
          : Text('Unavailable: not counted in the total',
              style: TextStyle(color: theme.colorScheme.error)),
      trailing: Row(mainAxisSize: MainAxisSize.min, children: [
        IconButton(
          tooltip: 'Decrease quantity',
          icon: const Icon(Icons.remove_circle_outline),
          onPressed: () => onSet(line.quantity - 1),
        ),
        Text('${line.quantity}', key: ValueKey('qty-${line.key}')),
        IconButton(
          tooltip: 'Increase quantity',
          icon: const Icon(Icons.add_circle_outline),
          onPressed: () => onSet(line.quantity + 1),
        ),
        IconButton(
          tooltip: 'Remove from cart',
          icon: const Icon(Icons.delete_outline),
          onPressed: onRemove,
        ),
      ]),
    );
  }
}
