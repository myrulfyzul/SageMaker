import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/network/app_failure.dart';
import '../../../../core/widgets/async_value_view.dart';
import '../../../../core/widgets/demo_label.dart';
import '../../analytics/ui/chart_cards.dart';
import '../../inventory/data/inventory_models.dart';
import '../../inventory/state/inventory_provider.dart';
import '../data/forecast_models.dart';
import '../state/forecast_provider.dart';

String _num(double v) =>
    v == v.roundToDouble() ? v.toInt().toString() : v.toStringAsFixed(2);

/// Text form of the forecast for screen readers (Req 26 accessibility).
String forecastSummary(Forecast f) {
  String join(List<MonthUnits> l) =>
      l.map((m) => '${shortMonth(m.month)}: ${_num(m.units)}').join('; ');
  return 'History: ${join(f.history)}. Baseline forecast: ${join(f.baseline)}.'
      '${f.candidate == null ? '' : ' Candidate forecast: ${join(f.candidate!)}.'}';
}

/// Demand forecast per product: history and predictions in one chart, MAE and
/// RMSE or "insufficient history", replenishment flag, methodology, Synthetic
/// data and Demo notices (Req 27.6, 27.10, 27.11).
class ForecastingScreen extends ConsumerStatefulWidget {
  const ForecastingScreen({super.key, this.initialProductId});
  final String? initialProductId;

  @override
  ConsumerState<ForecastingScreen> createState() => _ForecastingScreenState();
}

class _ForecastingScreenState extends ConsumerState<ForecastingScreen> {
  String? _productId;

  @override
  void initState() {
    super.initState();
    _productId = widget.initialProductId;
  }

  @override
  Widget build(BuildContext context) {
    final inventory = ref.watch(inventoryProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Forecasting')),
      body: ListView(children: [
        const Padding(
          padding: EdgeInsets.all(12),
          child: Align(
              alignment: Alignment.centerLeft,
              child: DemoLabel('Demo: forecasts use demonstration data')),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12),
          child: inventory.when(
            loading: () => const LinearProgressIndicator(),
            error: (e, _) => Text(e is AppFailure ? e.message : 'Server error'),
            data: (items) => DropdownButtonFormField<String>(
              key: const ValueKey('forecast-product'),
              initialValue: items.any((i) => i.productId == _productId) ? _productId : null,
              decoration: const InputDecoration(labelText: 'Product'),
              items: [
                for (final StockItem i in items)
                  DropdownMenuItem(value: i.productId, child: Text(i.name)),
              ],
              onChanged: (v) => setState(() => _productId = v),
            ),
          ),
        ),
        if (_productId == null)
          const Padding(
              padding: EdgeInsets.all(24),
              child: Center(child: Text('Select a product to see its forecast.')))
        else
          _ForecastBody(productId: _productId!),
      ]),
    );
  }
}

class _ForecastBody extends ConsumerWidget {
  const _ForecastBody({required this.productId});
  final String productId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final value = ref.watch(forecastProvider(productId));
    if (value.hasError && !value.hasValue) {
      // No chart or metrics on error (Req 27.11).
      final e = value.error;
      final msg = e is ValidationFailure
          ? 'This product has no sales history to forecast from.'
          : e is AppFailure
              ? e.message
              : AsyncValueView.defaultErrorMessage(e!);
      return Padding(
        padding: const EdgeInsets.all(24),
        child: Column(children: [
          Text(msg, textAlign: TextAlign.center),
          const SizedBox(height: 12),
          FilledButton(
              onPressed: () => ref.invalidate(forecastProvider(productId)),
              child: const Text('Retry')),
        ]),
      );
    }
    if (!value.hasValue) {
      return const Padding(
          padding: EdgeInsets.all(24),
          child: Center(child: CircularProgressIndicator()));
    }
    return ForecastView(forecast: value.requireValue);
  }
}

class ForecastView extends StatelessWidget {
  const ForecastView({super.key, required this.forecast});
  final Forecast forecast;

  @override
  Widget build(BuildContext context) {
    final f = forecast;
    final scheme = Theme.of(context).colorScheme;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      if (f.synthetic)
        Card(
          key: const ValueKey('synthetic-notice'),
          color: scheme.tertiaryContainer,
          margin: const EdgeInsets.all(12),
          child: const Padding(
            padding: EdgeInsets.all(12),
            child: Text('Synthetic data: this history was generated by the '
                'seed script, not real sales.'),
          ),
        ),
      if (f.replenish)
        Card(
          key: const ValueKey('replenish-flag'),
          color: scheme.errorContainer,
          margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
          child: const Padding(
            padding: EdgeInsets.all(12),
            child: Text('Replenish: current stock is below forecast demand '
                'for next month plus the low-stock threshold.'),
          ),
        )
      else
        const Padding(
          padding: EdgeInsets.symmetric(horizontal: 12, vertical: 6),
          child: Text('No replenishment needed.', key: ValueKey('no-replenish')),
        ),
      ChartCard(
        title: 'Units per month',
        summary: forecastSummary(f),
        isEmpty: f.history.isEmpty,
        chart: _ForecastChart(forecast: f),
      ),
      _Metrics(forecast: f),
      Padding(
        padding: const EdgeInsets.all(12),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('Methodology', style: Theme.of(context).textTheme.titleMedium),
          for (final e in f.methodology.entries)
            Padding(
              padding: const EdgeInsets.only(top: 6),
              child: Text('${_title(e.key)}: ${e.value}'),
            ),
        ]),
      ),
    ]);
  }

  static String _title(String k) =>
      k.isEmpty ? k : k[0].toUpperCase() + k.substring(1);
}

class _Metrics extends StatelessWidget {
  const _Metrics({required this.forecast});
  final Forecast forecast;

  @override
  Widget build(BuildContext context) {
    final f = forecast;
    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('Accuracy (backtest)', style: Theme.of(context).textTheme.titleMedium),
          if (!f.evaluationAvailable)
            const Text('Insufficient history', key: ValueKey('insufficient'))
          else ...[
            Text('Baseline: MAE ${_num(f.baselineMetrics!.mae)}, '
                'RMSE ${_num(f.baselineMetrics!.rmse)} units'),
            Text('Candidate: MAE ${_num(f.candidateMetrics!.mae)}, '
                'RMSE ${_num(f.candidateMetrics!.rmse)} units'),
          ],
          Text('Selected model: ${f.selectedModel}'),
        ]),
      ),
    );
  }
}

class _ForecastChart extends StatelessWidget {
  const _ForecastChart({required this.forecast});
  final Forecast forecast;

  @override
  Widget build(BuildContext context) {
    final f = forecast;
    final scheme = Theme.of(context).colorScheme;
    final n = f.history.length;
    final labels = [
      for (final m in f.history) m.month,
      for (final m in f.baseline) m.month,
    ];
    List<FlSpot> hist = [
      for (var i = 0; i < n; i++) FlSpot(i.toDouble(), f.history[i].units)
    ];
    List<FlSpot> future(List<MonthUnits> l) => [
          if (n > 0) hist.last,
          for (var i = 0; i < l.length; i++) FlSpot((n + i).toDouble(), l[i].units),
        ];
    LineChartBarData line(List<FlSpot> s, Color c, {bool dashed = false}) =>
        LineChartBarData(
          spots: s,
          color: c,
          isCurved: false,
          barWidth: 2,
          dotData: const FlDotData(show: true),
          dashArray: dashed ? [6, 4] : null,
        );
    const none = AxisTitles(sideTitles: SideTitles(showTitles: false));
    return Column(children: [
      Expanded(
        child: LineChart(LineChartData(
          lineBarsData: [
            line(hist, scheme.primary),
            line(future(f.baseline), scheme.secondary, dashed: true),
            if (f.candidate != null)
              line(future(f.candidate!), scheme.tertiary, dashed: true),
          ],
          gridData: const FlGridData(drawVerticalLine: false),
          borderData: FlBorderData(show: false),
          titlesData: FlTitlesData(
            topTitles: none,
            rightTitles: none,
            bottomTitles: AxisTitles(
              axisNameWidget: const Text('Month', style: TextStyle(fontSize: 11)),
              axisNameSize: 18,
              sideTitles: SideTitles(
                showTitles: true,
                reservedSize: 24,
                interval: 1,
                getTitlesWidget: (v, meta) {
                  final i = v.toInt();
                  if (i < 0 || i >= labels.length || (labels.length > 8 && i.isOdd)) {
                    return const SizedBox.shrink();
                  }
                  return SideTitleWidget(
                      meta: meta,
                      child: Text(shortMonth(labels[i]),
                          style: const TextStyle(fontSize: 9)));
                },
              ),
            ),
            leftTitles: AxisTitles(
              axisNameWidget: const Text('Units', style: TextStyle(fontSize: 11)),
              axisNameSize: 18,
              sideTitles: SideTitles(
                showTitles: true,
                reservedSize: 32,
                getTitlesWidget: (v, meta) => SideTitleWidget(
                    meta: meta,
                    child: Text(meta.formattedValue,
                        style: const TextStyle(fontSize: 10))),
              ),
            ),
          ),
        )),
      ),
      Wrap(spacing: 12, children: [
        _Legend(scheme.primary, 'History'),
        _Legend(scheme.secondary, 'Baseline'),
        if (f.candidate != null) _Legend(scheme.tertiary, 'Candidate'),
      ]),
    ]);
  }
}

class _Legend extends StatelessWidget {
  const _Legend(this.color, this.label);
  final Color color;
  final String label;

  @override
  Widget build(BuildContext context) => Row(mainAxisSize: MainAxisSize.min, children: [
        Container(width: 10, height: 10, color: color),
        const SizedBox(width: 4),
        Text(label, style: const TextStyle(fontSize: 11)),
      ]);
}
