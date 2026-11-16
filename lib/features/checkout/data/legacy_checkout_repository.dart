import '../../../core/network/api_client.dart';

/// Places a guest demo order through `POST /api/legacy/orders` (unchanged
/// request/response shape: `checkout_id`, ..., `items`; 201 with `accessToken`).
class LegacyCheckoutRepository {
  LegacyCheckoutRepository(this._client);

  final ApiClient _client;

  Future<Map<String, dynamic>> placeOrder(Map<String, dynamic> data) async {
    final body = await _client.post('/api/legacy/orders', body: data);
    return Map<String, dynamic>.from(body as Map);
  }
}
