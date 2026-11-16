import '../../../../core/network/api_client.dart';

class MonthUnits {
  const MonthUnits(this.month, this.units);
  final String month;
  final double units;

  factory MonthUnits.fromJson(Map<String, dynamic> j) =>
      MonthUnits((j['month'] ?? '').toString(), (j['units'] as num? ?? 0).toDouble());
}

class ModelMetrics {
  const ModelMetrics(this.mae, this.rmse);
  final double mae;
  final double rmse;
}

/// `GET /api/staff/forecast/{product_id}` (Req 27).
class Forecast {
  const Forecast({
    required this.productId,
    required this.synthetic,
    required this.history,
    required this.baseline,
    required this.candidate,
    required this.evaluationAvailable,
    required this.baselineMetrics,
    required this.candidateMetrics,
    required this.selectedModel,
    required this.replenish,
    required this.methodology,
  });

  factory Forecast.fromJson(Map<String, dynamic> j) {
    List<MonthUnits> months(Object? o) => [
          for (final e in (o as List? ?? const []))
            MonthUnits.fromJson(Map<String, dynamic>.from(e as Map))
        ];
    final cand = j['candidate'] is Map ? (j['candidate'] as Map)['forecast'] : null;
    final eval = j['evaluation'] is Map
        ? Map<String, dynamic>.from(j['evaluation'] as Map)
        : <String, dynamic>{};
    ModelMetrics? metrics(Object? o) => o is Map
        ? ModelMetrics((o['mae'] as num).toDouble(), (o['rmse'] as num).toDouble())
        : null;
    final available = eval['available'] == true;
    return Forecast(
      productId: (j['productId'] ?? '').toString(),
      synthetic: j['synthetic'] == true,
      history: months(j['history']),
      baseline: months((j['baseline'] as Map?)?['forecast']),
      candidate: cand == null ? null : months(cand),
      evaluationAvailable: available,
      baselineMetrics: available ? metrics(eval['baseline']) : null,
      candidateMetrics: available ? metrics(eval['candidate']) : null,
      selectedModel: (j['selectedModel'] ?? 'baseline').toString(),
      replenish: j['replenish'] == true,
      methodology: {
        for (final e in ((j['methodology'] as Map?) ?? const {}).entries)
          e.key.toString(): e.value.toString()
      },
    );
  }

  final String productId;
  final bool synthetic;
  final List<MonthUnits> history;
  final List<MonthUnits> baseline;
  final List<MonthUnits>? candidate;
  final bool evaluationAvailable;
  final ModelMetrics? baselineMetrics;
  final ModelMetrics? candidateMetrics;
  final String selectedModel;
  final bool replenish;
  final Map<String, String> methodology;
}

class ForecastRepository {
  ForecastRepository(this._client);
  final ApiClient _client;

  Future<Forecast> get(String productId) async {
    final body = await _client.get('/api/staff/forecast/$productId');
    return Forecast.fromJson(Map<String, dynamic>.from(body as Map));
  }
}
