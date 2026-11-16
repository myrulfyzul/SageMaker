import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/money.dart';
import '../../../../core/widgets/demo_label.dart';
import '../../../../core/widgets/loading_view.dart';
import '../data/analytics_models.dart';
import '../state/analytics_providers.dart';
import 'chart_cards.dart';

/// Sales analytics for a chosen date range (Req 26).
class AnalyticsScreen extends ConsumerWidget {
  const AnalyticsScreen({super.key});

  Future<void> _pick(BuildContext context, WidgetRef ref, bool isStart) async {
    final s = ref.read(analyticsProvider);
    final picked = await showDatePicker(
      context: context,
      initialDate: isStart ? s.start : s.end,
      firstDate: DateTime(2000),
      lastDate: DateTime.now().add(const Duration(days: 366)),
      helpText: isStart ? 'Start date' : 'End date',
    );
    if (picked == null) return;
    final n = ref.read(analyticsProvider.notifier);
    await (isStart ? n.setRange(start: picked) : n.setRange(end: picked));
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final s = ref.watch(analyticsProvider);
    final r = s.report;
    return Scaffold(
      appBar: AppBar(title: const Text('Analytics')),
      body: ListView(
        children: [
          Padding(
            padding: const EdgeInsets.all(12),
            child: Row(children: [
              Expanded(
                child: OutlinedButton.icon(
                  icon: const Icon(Icons.date_range),
                  label: Text('Start ${isoDate(s.start)}'),
                  onPressed: () => _pick(context, ref, true),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: OutlinedButton.icon(
                  icon: const Icon(Icons.date_range),
                  label: Text('End ${isoDate(s.end)}'),
                  onPressed: () => _pick(context, ref, false),
                ),
              ),
            ]),
          ),
          if (s.rangeError != null)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12),
              child: Text(s.rangeError!,
                  style: TextStyle(color: Theme.of(context).colorScheme.error)),
            ),
          if (s.loadFailed)
            MaterialBanner(
              content: const Text('Could not load analytics.'),
              actions: [
                TextButton(
                    onPressed: ref.read(analyticsProvider.notifier).load,
                    child: const Text('Retry')),
              ],
            ),
          if (r == null && s.loading) const SizedBox(height: 200, child: LoadingView()),
          if (r != null) ...[
            if (r.orderCount > 0)
              const Padding(
                padding: EdgeInsets.fromLTRB(12, 0, 12, 4),
                child: Align(
                    alignment: Alignment.centerLeft,
                    child: DemoLabel('Demo data')),
              ),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 8),
              child: Row(children: [
                Expanded(child: SizedBox(height: 92, child: KpiCard(label: 'Revenue', value: formatRm(r.totalRevenueSen)))),
                Expanded(child: SizedBox(height: 92, child: KpiCard(label: 'Orders', value: '${r.orderCount}'))),
                Expanded(child: SizedBox(height: 92, child: KpiCard(label: 'AOV', value: formatRm(r.aovSen)))),
              ]),
            ),
            ChartCard(
              title: 'Revenue by month',
              summary: monthlySummary(r.monthly),
              isEmpty: r.monthlyEmpty,
              chart: MonthlyRevenueChart(months: r.monthly),
            ),
            _productsCard('Top 5 products', r.topProducts),
            _productsCard('Bottom 5 products', r.bottomProducts),
          ],
          const SizedBox(height: 16),
        ],
      ),
    );
  }

  Widget _productsCard(String title, List<ProductUnits> items) => ChartCard(
        title: title,
        summary: productsSummary(items),
        isEmpty: items.isEmpty,
        chart: LabelledBarChart(
          labels: [for (final p in items) p.name],
          values: [for (final p in items) p.units],
          xTitle: 'Product',
          yTitle: 'Units sold',
        ),
      );
}

