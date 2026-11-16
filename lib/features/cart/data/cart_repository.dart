import '../../../core/network/api_client.dart';
import 'cart_models.dart';

/// Server cart (`/api/cart`, customer only).
class CartRepository {
  CartRepository(this.client);
  final ApiClient client;

  CartData _cart(dynamic body) =>
      CartData.fromJson(Map<String, dynamic>.from(body as Map));

  Future<CartData> fetch() async => _cart(await client.get('/api/cart'));

  Future<CartData> add(String productId, int? variationId, int quantity) async =>
      _cart(await client.post('/api/cart/lines', body: {
        'productId': productId,
        'variationId': variationId,
        'quantity': quantity,
      }));

  /// Sets the quantity of a line; 0 removes it (Req 11.8).
  Future<CartData> setQuantity(
          String productId, int? variationId, int quantity) async =>
      _cart(await client.put('/api/cart/lines', body: {
        'productId': productId,
        'variationId': variationId,
        'quantity': quantity,
      }));

  Future<CartData> remove(int lineId) async =>
      _cart(await client.delete('/api/cart/lines/$lineId'));

  /// Merges guest lines (product id to quantity, keyed by [cartKey]).
  Future<MergeResult> merge(Map<String, int> guest) async {
    final body = await client.post('/api/cart/merge', body: {
      'lines': [
        for (final e in guest.entries)
          {
            'productId': parseCartKey(e.key).productId,
            'variationId': parseCartKey(e.key).variationId,
            'quantity': e.value,
          },
      ],
    });
    final map = Map<String, dynamic>.from(body as Map);
    return MergeResult(
      _cart(map['cart']),
      [
        for (final n in (map['notMerged'] as List? ?? const []))
          if (NotMergedItem.tryParse(n) case final item?) item,
      ],
    );
  }
}
