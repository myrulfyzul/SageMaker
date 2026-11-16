import '../../../core/network/api_client.dart';
import '../../../core/storage/legacy_local_store.dart';

export '../../../core/storage/legacy_local_store.dart' show SavedOrder;

const legacyOrderTimeout = Duration(seconds: 10);

/// Orders placed as a guest by the earlier prototype. They are read once from
/// the old `sagemaker_demo_orders_v1` key and tracked through
/// `GET /api/legacy/orders/{id}` with the saved `X-Order-Token`; the My Orders
/// screen lists them as legacy guest orders.
class LegacyOrdersRepository {
  LegacyOrdersRepository(this._store, this._client);

  final LegacyLocalStore _store;
  final ApiClient _client;

  List<SavedOrder> load() => _store.readOrders();

  /// Adds [order] at the top of the saved list (newest first) and persists it.
  Future<List<SavedOrder>> add(List<SavedOrder> current, SavedOrder order) async {
    final next = [order, ...current.where((o) => o.id != order.id)];
    await _store.writeOrders(next);
    return next;
  }

  Future<Map<String, dynamic>> getOrder(SavedOrder saved) async {
    final body = await _client.get(
      '/api/legacy/orders/${Uri.encodeComponent(saved.id)}',
      headers: {'X-Order-Token': saved.token},
      timeout: legacyOrderTimeout,
    );
    return Map<String, dynamic>.from(body as Map);
  }
}
