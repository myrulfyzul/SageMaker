import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../../core/money.dart';
import '../../../../core/widgets/async_value_view.dart';
import '../../../../core/widgets/error_view.dart';
import '../../../../core/widgets/loading_view.dart';
import '../../../orders/data/order_models.dart';
import '../data/staff_orders_repository.dart';
import '../state/staff_orders_provider.dart';

/// Staff Orders list: newest first, status filter, search by order id or
/// customer name, and paging (Req 22.1 to 22.4). Legacy orders are listed
/// like any other (Req 22.13).
class StaffOrdersScreen extends ConsumerStatefulWidget {
  const StaffOrdersScreen({super.key});

  @override
  ConsumerState<StaffOrdersScreen> createState() => _StaffOrdersScreenState();
}

class _StaffOrdersScreenState extends ConsumerState<StaffOrdersScreen> {
  final _search = TextEditingController();

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final value = ref.watch(staffOrdersProvider);
    final notifier = ref.read(staffOrdersProvider.notifier);
    final selected = value.value?.status;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Orders'),
        actions: [
          IconButton(
            tooltip: 'Custom orders',
            icon: const Icon(Icons.brush_outlined),
            onPressed: () => context.push('/staff/orders/custom-orders'),
          ),
          IconButton(
            tooltip: 'Refresh',
            icon: const Icon(Icons.refresh),
            onPressed: notifier.refresh,
          ),
        ],
      ),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 8, 12, 4),
            child: TextField(
              key: const ValueKey('staff-orders-search'),
              controller: _search,
              maxLength: 100,
              textInputAction: TextInputAction.search,
              decoration: InputDecoration(
                labelText: 'Search by order ID or customer',
                counterText: '',
                prefixIcon: const Icon(Icons.search),
                suffixIcon: IconButton(
                  tooltip: 'Clear search',
                  icon: const Icon(Icons.clear),
                  onPressed: () {
                    _search.clear();
                    notifier.setQuery('');
                  },
                ),
              ),
              onSubmitted: notifier.setQuery,
            ),
          ),
          SizedBox(
            height: 48,
            child: ListView(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.symmetric(horizontal: 8),
              children: [
                _FilterChip(
                    label: 'All',
                    selected: selected == null,
                    onSelected: () => notifier.setStatus(null)),
                for (final s in staffOrderStatuses)
                  _FilterChip(
                      label: orderStatusLabel(s),
                      selected: selected == s,
                      onSelected: () => notifier.setStatus(s)),
              ],
            ),
          ),
          Expanded(child: _body(context, value)),
        ],
      ),
    );
  }

  Widget _body(BuildContext context, AsyncValue<StaffOrdersState> value) {
    final notifier = ref.read(staffOrdersProvider.notifier);
    if (!value.hasValue) {
      if (value.hasError) {
        return ErrorView(
            message: AsyncValueView.defaultErrorMessage(value.error!),
            onRetry: notifier.retry);
      }
      return const LoadingView();
    }
    final s = value.requireValue;
    return Column(
      children: [
        if (s.refreshFailed)
          MaterialBanner(
            content:
                const Text('Refresh failed. Showing the last loaded orders.'),
            actions: [
              TextButton(
                  onPressed: notifier.refresh, child: const Text('Retry')),
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
                    padding: EdgeInsets.all(24),
                    child:
                        Text('No orders match.', textAlign: TextAlign.center),
                  ),
                for (final o in s.orders) _StaffOrderTile(order: o),
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
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class _FilterChip extends StatelessWidget {
  const _FilterChip(
      {required this.label, required this.selected, required this.onSelected});
  final String label;
  final bool selected;
  final VoidCallback onSelected;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.symmetric(horizontal: 4),
        child: ChoiceChip(
          key: ValueKey('filter-$label'),
          label: Text(label),
          selected: selected,
          onSelected: (_) => onSelected(),
        ),
      );
}

class _StaffOrderTile extends StatelessWidget {
  const _StaffOrderTile({required this.order});
  final StaffOrderSummary order;

  @override
  Widget build(BuildContext context) {
    final date = order.createdAt == null
        ? ''
        : '${formatLocalDateTime(order.createdAt!)} · ';
    return ListTile(
      key: ValueKey('staff-order-${order.id}'),
      title: Text('${order.id} · ${order.customerName}'),
      subtitle: Text('$date${orderStatusLabel(order.status)}'),
      trailing: Text(formatRm(order.totalSen)),
      onTap: () =>
          context.push('/staff/orders/${Uri.encodeComponent(order.id)}'),
    );
  }
}
