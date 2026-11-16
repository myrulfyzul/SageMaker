import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/money.dart';
import '../../../core/network/app_failure.dart';
import '../../../core/storage/legacy_local_store.dart';
import '../../../core/widgets/async_value_view.dart';
import '../../../core/widgets/empty_view.dart';
import '../../../core/widgets/error_view.dart';
import '../../../core/widgets/loading_view.dart';
import '../data/order_models.dart';
import '../state/my_orders_provider.dart';
import '../state/orders_store.dart';
import 'order_detail_page.dart';

/// My Orders: newest first, paged, with the last data kept when a refresh
/// fails and a section for legacy guest orders saved on this device
/// (Req 15.1, 15.2, 15.9).
class MyOrdersScreen extends ConsumerWidget {
  const MyOrdersScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final value = ref.watch(myOrdersProvider);
    final notifier = ref.read(myOrdersProvider.notifier);
    final legacy = _legacyOrders(ref);
    return Scaffold(
      appBar: AppBar(
        title: const Text('My orders'),
        actions: [
          IconButton(
            tooltip: 'Refresh',
            icon: const Icon(Icons.refresh),
            onPressed: notifier.refresh,
          ),
        ],
      ),
      body: _body(context, ref, value, legacy),
    );
  }

  Widget _body(BuildContext context, WidgetRef ref,
      AsyncValue<MyOrdersState> value, List<SavedOrder> legacy) {
    final notifier = ref.read(myOrdersProvider.notifier);
    if (!value.hasValue) {
      if (value.hasError) {
        return ErrorView(
            message: AsyncValueView.defaultErrorMessage(value.error!),
            onRetry: notifier.retry);
      }
      return const LoadingView();
    }
    final s = value.requireValue;
    if (s.orders.isEmpty && legacy.isEmpty) {
      return EmptyView(
        message: 'You have no orders yet.',
        actionLabel: 'Explore products',
        onAction: () => context.go('/shop'),
      );
    }
    return Column(
      children: [
        if (s.refreshFailed)
          MaterialBanner(
            content: const Text('Refresh failed. Showing your last loaded orders.'),
            actions: [
              TextButton(onPressed: notifier.refresh, child: const Text('Retry')),
            ],
          ),
        Expanded(
          child: RefreshIndicator(
            onRefresh: notifier.refresh,
            child: ListView(
              physics: const AlwaysScrollableScrollPhysics(),
              children: [
                if (s.orders.isEmpty)
                  const Padding(
                    padding: EdgeInsets.all(16),
                    child: Text('You have no orders yet.'),
                  ),
                for (final o in s.orders) _OrderTile(order: o),
                if (s.hasMore)
                  Padding(
                    padding: const EdgeInsets.all(12),
                    child: s.loadingMore
                        ? const Center(child: CircularProgressIndicator())
                        : OutlinedButton(
                            onPressed: notifier.loadMore,
                            child: const Text('Load more'),
                          ),
                  ),
                if (legacy.isNotEmpty) ...[
                  const Padding(
                    padding: EdgeInsets.fromLTRB(16, 20, 16, 4),
                    child: Text('Legacy guest orders',
                        style: TextStyle(fontWeight: FontWeight.w700)),
                  ),
                  const Padding(
                    padding: EdgeInsets.symmetric(horizontal: 16),
                    child: Text(
                        'Orders placed as a guest on this device before you signed in.'),
                  ),
                  for (final saved in legacy) _LegacyTile(saved: saved),
                ],
              ],
            ),
          ),
        ),
      ],
    );
  }

  List<SavedOrder> _legacyOrders(WidgetRef ref) {
    if (!ref.watch(legacyLocalStoreProvider).hasValue) return const [];
    final store = ref.watch(ordersStoreProvider);
    return List.of(store.saved);
  }
}

class _OrderTile extends StatelessWidget {
  const _OrderTile({required this.order});
  final OrderSummary order;

  @override
  Widget build(BuildContext context) {
    final date = order.createdAt == null ? '' : '${formatLocalDateTime(order.createdAt!)} · ';
    return ListTile(
      key: ValueKey('order-${order.id}'),
      title: Text(order.id),
      subtitle: Text(
          '$date${orderStatusLabel(order.status)} · ${order.itemCount} item${order.itemCount == 1 ? '' : 's'}'),
      trailing: Text(formatRm(order.totalSen)),
      onTap: () => context.push('/orders/${order.id}'),
    );
  }
}

class _LegacyTile extends ConsumerWidget {
  const _LegacyTile({required this.saved});
  final SavedOrder saved;

  @override
  Widget build(BuildContext context, WidgetRef ref) => ListTile(
        key: ValueKey('legacy-${saved.id}'),
        leading: const Icon(Icons.history),
        title: Text(saved.id),
        subtitle: const Text('Legacy guest order'),
        trailing: const Icon(Icons.chevron_right),
        onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(
            builder: (_) => OrderDetailPage(
                saved: saved, orders: ref.read(ordersStoreProvider)))),
      );
}

/// Used by the order screen to explain a failed first load.
String orderLoadErrorMessage(Object error) => error is NotFoundFailure
    ? 'Order not found.'
    : AsyncValueView.defaultErrorMessage(error);
