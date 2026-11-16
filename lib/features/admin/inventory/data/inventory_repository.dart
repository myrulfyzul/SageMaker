import '../../../../core/network/api_client.dart';
import 'inventory_models.dart';

/// `/api/staff/inventory` (Req 21).
class InventoryRepository {
  InventoryRepository(this._client);

  final ApiClient _client;

  Future<List<StockItem>> list({bool lowOnly = false}) async {
    final all = <StockItem>[];
    while (true) {
      final body = await _client.get('/api/staff/inventory', query: {
        'limit': 100,
        'offset': all.length,
        if (lowOnly) 'low_only': 'true',
      });
      final rows = body is Map ? (body['items'] as List? ?? const []) : body as List;
      all.addAll(rows.map(
          (r) => StockItem.fromJson(Map<String, dynamic>.from(r as Map))));
      final total = body is Map ? (body['total'] as num?)?.toInt() : null;
      if (rows.isEmpty || total == null || all.length >= total) return all;
    }
  }

  Future<void> adjust(String productId, int delta, String reason) async {
    await _client.post('/api/staff/inventory/$productId/adjustments',
        body: {'delta': delta, 'reason': reason.trim()});
  }

  Future<void> setThreshold(String productId, int threshold) async {
    await _client.put('/api/staff/inventory/$productId/threshold',
        body: {'lowStockThreshold': threshold});
  }

  /// Newest first (Req 21.7).
  Future<List<StockAdjustment>> history(String productId) async {
    final body =
        await _client.get('/api/staff/inventory/$productId/adjustments');
    final rows = body is Map ? (body['items'] as List? ?? const []) : (body as List? ?? const []);
    return rows
        .map((r) =>
            StockAdjustment.fromJson(Map<String, dynamic>.from(r as Map)))
        .toList();
  }
}
