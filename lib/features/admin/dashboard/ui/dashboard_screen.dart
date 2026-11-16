import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/money.dart';
import '../../../../core/widgets/error_view.dart';
import '../../../../core/widgets/loading_view.dart';
import '../../analytics/data/analytics_models.dart';
import '../../analytics/state/analytics_providers.dart';
import '../../analytics/ui/chart_cards.dart';

/// Staff dashboard: KPIs and four chart series (Req 19.2 to 19.9).
class DashboardScreen extends ConsumerWidget {
  const DashboardScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final value = ref.watch(dashboardProvider);
    final notifier = ref.read(dashboardProvider.notifier);
    if (!value.hasValue) {
      if (value.hasError) {
        return ErrorView(
            message: 'Could not load the dashboard.', onRetry: notifier.retry);
      }
      return const LoadingView();
    }
    final loaded = value.requireValue;
    final d = loaded.data;
    return RefreshIndicator(
      onRefresh: notifier.refresh,
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        children: [
          if (loaded.refreshFailed)
            MaterialBanner(
              content: const Text('Could not load the dashboard.'),
              actions: [
                TextButton(
                    onPressed: notifier.retry, child: const Text('Retry')),
              ],
            ),
          const _Greeting(),
          _KpiGrid(kpis: d.kpis),
          ChartCard(
            title: 'Sales by month',
            summary: monthlySummary(d.salesByMonth),
            isEmpty: d.salesEmpty,
            chart: MonthlyRevenueChart(months: d.salesByMonth),
          ),
          ChartCard(
            title: 'Orders by status',
            summary: d.ordersByStatus.entries
                .map((e) => '${e.key}: ${e.value}')
                .join('; '),
            isEmpty: d.statusEmpty,
            chart: LabelledBarChart(
              labels: d.ordersByStatus.keys.toList(),
              values: d.ordersByStatus.values.toList(),
              xTitle: 'Status',
              yTitle: 'Orders',
            ),
          ),
          ChartCard(
            title: 'Best-selling products',
            summary: productsSummary(d.bestSellers),
            isEmpty: d.bestSellers.isEmpty,
            chart: LabelledBarChart(
              labels: [for (final p in d.bestSellers) p.name],
              values: [for (final p in d.bestSellers) p.units],
              xTitle: 'Product',
              yTitle: 'Units',
            ),
          ),
          ChartCard(
            title: 'Inventory by category',
            summary: d.inventoryByCategory
                .map((c) => '${c.category}: ${c.units} units')
                .join('; '),
            isEmpty: d.inventoryEmpty,
            chart: CategoryPieChart(items: d.inventoryByCategory),
          ),
          const SizedBox(height: 16),
        ],
      ),
    );
  }
}

class _KpiGrid extends StatelessWidget {
  const _KpiGrid({required this.kpis});
  final DashboardKpis kpis;

  @override
  Widget build(BuildContext context) {
    final items = [
      ('Revenue', formatRm(kpis.totalRevenueSen), Icons.payments_outlined),
      ('Orders', '${kpis.orderCount}', Icons.receipt_long_outlined),
      ('Pending', '${kpis.pendingOrders}', Icons.pending_actions_outlined),
      ('AOV', formatRm(kpis.aovSen), Icons.shopping_basket_outlined),
      ('Low stock', '${kpis.lowStockCount}', Icons.warning_amber_rounded),
      (
        'Open production',
        '${kpis.openProductionJobs}',
        Icons.handyman_outlined
      ),
      ('Shipped', '${kpis.shippedOrderCount}', Icons.local_shipping_outlined),
    ];
    return GridView(
      gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
          crossAxisCount: 2, mainAxisExtent: 76),
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      padding: const EdgeInsets.all(8),
      children: [
        for (final (n, i) in items.indexed)
          KpiCard(label: i.$1, value: i.$2, icon: i.$3, highlight: n == 0),
      ],
    );
  }
}

class _Greeting extends StatelessWidget {
  const _Greeting();

  @override
  Widget build(BuildContext context) {
    final hour = DateTime.now().hour;
    final hello = hour < 12
        ? 'Selamat pagi'
        : hour < 19
            ? 'Selamat petang'
            : 'Selamat malam';
    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 12, 12, 4),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(hello, style: Theme.of(context).textTheme.bodySmall),
        Text("Here's how the store is doing",
            style: Theme.of(context).textTheme.headlineSmall),
      ]),
    );
  }
}
