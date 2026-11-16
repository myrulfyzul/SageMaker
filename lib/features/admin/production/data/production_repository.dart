import '../../../../core/network/api_client.dart';
import 'production_models.dart';

/// `/api/production/jobs` (Req 24, 6.7, 6.8). The server limits an
/// Artisan_User to their own jobs.
class ProductionRepository {
  ProductionRepository(this._client);

  final ApiClient _client;

  Future<List<ProductionJob>> list(ProductionFilters f) async {
    final all = <ProductionJob>[];
    while (true) {
      final body = await _client.get('/api/production/jobs', query: {
        'view': 'list',
        'limit': 100,
        'offset': all.length,
        if (f.status != null) 'status': f.status,
        if (f.artisanId != null) 'artisan_id': f.artisanId,
        if (f.priority != null) 'priority': f.priority,
      });
      final rows =
          body is Map ? (body['items'] as List? ?? const []) : body as List;
      all.addAll(rows.map((r) =>
          ProductionJob.fromJson(Map<String, dynamic>.from(r as Map))));
      final total = body is Map ? (body['total'] as num?)?.toInt() : null;
      if (rows.isEmpty || total == null || all.length >= total) return all;
    }
  }

  Future<ProductionJob> get(int id) async => ProductionJob.fromJson(
      Map<String, dynamic>.from(
          await _client.get('/api/production/jobs/$id') as Map));

  Future<ProductionJob> assign(
    int id, {
    required int artisanId,
    required int quantity,
    required String deadline,
    required String priority,
    required String notes,
  }) async =>
      ProductionJob.fromJson(Map<String, dynamic>.from(await _client.post(
          '/api/production/jobs/$id/assign',
          body: {
            'artisanId': artisanId,
            'quantity': quantity,
            'deadline': deadline,
            'priority': priority,
            'notes': notes,
          }) as Map));

  Future<ProductionJob> changeStatus(int id, String status) async =>
      ProductionJob.fromJson(Map<String, dynamic>.from(await _client
          .post('/api/production/jobs/$id/status',
              body: {'status': status}) as Map));

  Future<ProductionJob> addProgress(int id, int percent, String note) async =>
      ProductionJob.fromJson(Map<String, dynamic>.from(await _client.post(
          '/api/production/jobs/$id/progress',
          body: {'percent': percent, 'note': note}) as Map));
}
