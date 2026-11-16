import '../../../core/network/api_client.dart';
import 'order_models.dart';

const ordersPageSize = 20;

/// `GET /api/orders` and `GET /api/orders/{id}` for the signed-in customer.
class OrdersRepository {
  OrdersRepository(this._client);

  final ApiClient _client;

  Future<OrderPage> list({int offset = 0, int limit = ordersPageSize}) async {
    final body = await _client
        .get('/api/orders', query: {'limit': limit, 'offset': offset});
    return OrderPage.fromJson(Map<String, dynamic>.from(body as Map));
  }

  Future<OrderDetail> get(String id) async {
    final body =
        await _client.get('/api/orders/${Uri.encodeComponent(id)}');
    return OrderDetail.fromJson(Map<String, dynamic>.from(body as Map));
  }
}
