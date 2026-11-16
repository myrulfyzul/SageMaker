import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';

import '../../../../core/money.dart';
import '../data/analytics_models.dart';

/// Card with a title, a chart that is hidden from screen readers in favour of
/// a text summary (Req 19.4, 26), and an empty state (Req 19.9).
class ChartCard extends StatelessWidget {
  const ChartCard({
    super.key,
    required this.title,
    required this.summary,
    required this.isEmpty,
    required this.chart,
    this.emptyMessage = 'No data yet.',
  });

  final String title;

  /// Text form of the values, read by screen readers.
  final String summary;
  final bool isEmpty;
  final Widget chart;
  final String emptyMessage;

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            if (isEmpty)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 24),
                child: Center(child: Text(emptyMessage)),
              )
            else
              Semantics(
                container: true,
                label: '$title. $summary',
                child: ExcludeSemantics(child: SizedBox(height: 220, child: chart)),
              ),
          ],
        ),
      ),
    );
  }
}

String shortMonth(String ym) {
  const names = [
    'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec' //
  ];
  if (ym.length < 7) return ym;
  final m = int.tryParse(ym.substring(5, 7)) ?? 0;
  if (m < 1 || m > 12) return ym;
  return "${names[m - 1]} '${ym.substring(2, 4)}";
}

AxisTitles _axis(String name, {Widget Function(double, TitleMeta)? labels, double size = 28}) =>
    AxisTitles(
      axisNameWidget: Text(name, style: const TextStyle(fontSize: 11)),
      axisNameSize: 18,
      sideTitles: SideTitles(
        showTitles: labels != null,
        reservedSize: size,
        getTitlesWidget: labels ?? (v, m) => const SizedBox.shrink(),
      ),
    );

const _noTitles = AxisTitles(sideTitles: SideTitles(showTitles: false));

Widget _label(TitleMeta meta, String text) => SideTitleWidget(
      meta: meta,
      child: Text(text, style: const TextStyle(fontSize: 10)),
    );

String monthlySummary(List<MonthSales> months) => months
    .map((m) => '${shortMonth(m.month)}: ${formatRm(m.revenueSen)}, ${m.orderCount} orders')
    .join('; ');

/// Revenue per month as a bar chart (x: month, y: revenue in RM).
class MonthlyRevenueChart extends StatelessWidget {
  const MonthlyRevenueChart({super.key, required this.months});
  final List<MonthSales> months;

  @override
  Widget build(BuildContext context) {
    final color = Theme.of(context).colorScheme.primary;
    return BarChart(BarChartData(
      barGroups: [
        for (var i = 0; i < months.length; i++)
          BarChartGroupData(x: i, barRods: [
            BarChartRodData(toY: months[i].revenueSen / 100, color: color, width: 10),
          ]),
      ],
      gridData: const FlGridData(drawVerticalLine: false),
      borderData: FlBorderData(show: false),
      titlesData: FlTitlesData(
        topTitles: _noTitles,
        rightTitles: _noTitles,
        bottomTitles: _axis('Month', size: 24, labels: (v, meta) {
          final i = v.toInt();
          if (i < 0 || i >= months.length) return const SizedBox.shrink();
          // Thin out labels when there are many months.
          if (months.length > 8 && i.isOdd) return const SizedBox.shrink();
          return _label(meta, shortMonth(months[i].month));
        }),
        leftTitles: _axis('Revenue (RM)', size: 44, labels: (v, meta) => _label(meta, meta.formattedValue)),
      ),
    ));
  }
}

/// A generic labelled bar chart: one bar per entry.
class LabelledBarChart extends StatelessWidget {
  const LabelledBarChart({
    super.key,
    required this.labels,
    required this.values,
    required this.xTitle,
    required this.yTitle,
  });

  final List<String> labels;
  final List<int> values;
  final String xTitle;
  final String yTitle;

  @override
  Widget build(BuildContext context) {
    final color = Theme.of(context).colorScheme.secondary;
    return BarChart(BarChartData(
      barGroups: [
        for (var i = 0; i < values.length; i++)
          BarChartGroupData(x: i, barRods: [
            BarChartRodData(toY: values[i].toDouble(), color: color, width: 14),
          ]),
      ],
      gridData: const FlGridData(drawVerticalLine: false),
      borderData: FlBorderData(show: false),
      titlesData: FlTitlesData(
        topTitles: _noTitles,
        rightTitles: _noTitles,
        bottomTitles: _axis(xTitle, size: 28, labels: (v, meta) {
          final i = v.toInt();
          if (i < 0 || i >= labels.length) return const SizedBox.shrink();
          final t = labels[i];
          return _label(meta, t.length > 8 ? '${t.substring(0, 7)}.' : t);
        }),
        leftTitles: _axis(yTitle, size: 32, labels: (v, meta) => _label(meta, meta.formattedValue)),
      ),
    ));
  }
}

/// Stock units per category as a pie chart with a legend.
class CategoryPieChart extends StatelessWidget {
  const CategoryPieChart({super.key, required this.items});
  final List<CategoryUnits> items;

  static const _palette = [
    Colors.indigo, Colors.teal, Colors.orange, Colors.pink,
    Colors.green, Colors.purple, Colors.brown, Colors.blueGrey //
  ];

  @override
  Widget build(BuildContext context) {
    final shown = items.where((c) => c.units > 0).toList();
    return Row(children: [
      Expanded(
        child: PieChart(PieChartData(
          sectionsSpace: 2,
          centerSpaceRadius: 28,
          sections: [
            for (var i = 0; i < shown.length; i++)
              PieChartSectionData(
                value: shown[i].units.toDouble(),
                color: _palette[i % _palette.length],
                title: '${shown[i].units}',
                radius: 48,
                titleStyle: const TextStyle(fontSize: 11, color: Colors.white),
              ),
          ],
        )),
      ),
      Expanded(
        child: ListView(children: [
          for (var i = 0; i < shown.length; i++)
            Row(children: [
              Container(width: 10, height: 10, color: _palette[i % _palette.length]),
              const SizedBox(width: 6),
              Expanded(child: Text('${shown[i].category} (${shown[i].units})', style: const TextStyle(fontSize: 12))),
            ]),
        ]),
      ),
    ]);
  }
}

/// KPI tile: label and value.
class KpiCard extends StatelessWidget {
  const KpiCard({super.key, required this.label, required this.value});
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      container: true,
      label: '$label: $value',
      child: ExcludeSemantics(
        child: Card(
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(label, style: Theme.of(context).textTheme.labelMedium),
                const SizedBox(height: 4),
                FittedBox(
                  fit: BoxFit.scaleDown,
                  child: Text(value, style: Theme.of(context).textTheme.titleLarge),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

String productsSummary(List<ProductUnits> items) =>
    items.map((p) => '${p.name}: ${p.units} units').join('; ');
