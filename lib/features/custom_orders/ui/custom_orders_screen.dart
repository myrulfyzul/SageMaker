import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/money.dart';
import '../../../core/widgets/async_value_view.dart';
import '../../../core/widgets/empty_view.dart';
import '../../../core/widgets/error_view.dart';
import '../../../core/widgets/loading_view.dart';
import '../data/custom_order_models.dart';
import '../state/custom_orders_provider.dart';

/// Custom Orders list: the customer's own requests, newest first, showing
/// product type, quantity, preferred date, status and estimate
/// (Req 16.5, 16.6, 16.7).
class CustomOrdersScreen extends ConsumerWidget {
  const CustomOrdersScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final value = ref.watch(customOrdersProvider);
    return Scaffold(
      appBar: AppBar(
        title: const Text('Custom orders'),
        actions: [
          IconButton(
            tooltip: 'Refresh',
            icon: const Icon(Icons.refresh),
            onPressed: () => ref.invalidate(customOrdersProvider),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => context.push('/custom-orders/new'),
        icon: const Icon(Icons.add),
        label: const Text('New request'),
      ),
      body: value.when(
        loading: () => const LoadingView(),
        error: (e, _) => ErrorView(
            message: AsyncValueView.defaultErrorMessage(e),
            onRetry: () => ref.invalidate(customOrdersProvider)),
        data: (items) => items.isEmpty
            ? EmptyView(
                message: 'You have no custom orders yet.',
                actionLabel: 'Request a custom order',
                onAction: () => context.push('/custom-orders/new'),
              )
            : RefreshIndicator(
                onRefresh: () => ref.refresh(customOrdersProvider.future),
                child: ListView.builder(
                  physics: const AlwaysScrollableScrollPhysics(),
                  padding: const EdgeInsets.only(bottom: 88),
                  itemCount: items.length,
                  itemBuilder: (_, i) => _Tile(order: items[i]),
                ),
              ),
      ),
    );
  }
}

class _Tile extends StatelessWidget {
  const _Tile({required this.order});
  final CustomOrder order;

  @override
  Widget build(BuildContext context) {
    final price = order.estimatedPriceSen;
    return ListTile(
      key: ValueKey('custom-order-${order.id}'),
      title: Text(order.productType),
      subtitle: Text('Qty ${order.quantity} · Preferred ${order.preferredDate}'
          '${price == null ? '' : '\nEstimate ${formatRm(price)}'}'),
      isThreeLine: price != null,
      trailing: Chip(label: Text(customOrderStatusLabel(order.status))),
      onTap: () => context.push('/custom-orders/${order.id}'),
    );
  }
}
