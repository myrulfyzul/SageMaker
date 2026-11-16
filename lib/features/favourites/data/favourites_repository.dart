import '../../../core/network/api_client.dart';
import '../../../core/network/app_failure.dart';
import '../../catalogue/data/product.dart';

/// `/api/favourites` calls for a signed-in Customer (Req 10).
class FavouritesRepository {
  FavouritesRepository(this._client);
  final ApiClient _client;

  /// Active favourites, newest first. Uses the 10 s limit of Req 10.8.
  Future<List<Product>> list() async =>
      _items(await _client.get('/api/favourites', timeout: reachabilityTimeout));

  Future<void> add(String productId) =>
      _client.put('/api/favourites/${Uri.encodeComponent(productId)}');

  Future<void> remove(String productId) =>
      _client.delete('/api/favourites/${Uri.encodeComponent(productId)}');

  /// Uploads locally saved ids. Returns the merged server list; throws
  /// [AppFailure] unless the server confirmed the merge (Req 10.10).
  Future<List<Product>> merge(Iterable<String> productIds) async => _items(
      await _client.post('/api/favourites/merge',
          body: {'productIds': productIds.toList()}));

  List<Product> _items(dynamic data) {
    final items = data is Map ? data['items'] : null;
    if (items is! List) {
      throw const ServerFailure(message: 'Unexpected response');
    }
    return [
      for (final e in items)
        Product.fromJson(Map<String, dynamic>.from(e as Map)),
    ];
  }
}
