import 'dart:typed_data';

import 'package:http/http.dart' as http;

import '../../../../core/network/api_client.dart';
import 'admin_product_models.dart';

/// `/api/staff/products` (Req 20).
class AdminProductsRepository {
  AdminProductsRepository(this._client);

  final ApiClient _client;

  String _absolute(String url) =>
      url.startsWith('/') ? '${_client.baseUrl}$url' : url;

  AdminProduct _parse(dynamic body) {
    final p = AdminProduct.fromJson(Map<String, dynamic>.from(body as Map));
    return AdminProduct(
      id: p.id,
      name: p.name,
      description: p.description,
      categoryId: p.categoryId,
      categoryName: p.categoryName,
      priceSen: p.priceSen,
      stock: p.stock,
      lowStockThreshold: p.lowStockThreshold,
      isActive: p.isActive,
      imageUrls: p.imageUrls.map(_absolute).toList(),
    );
  }

  Future<AdminProductPage> list(
      {String q = '', int limit = 100, int offset = 0}) async {
    final body = await _client.get('/api/staff/products', query: {
      'limit': limit,
      'offset': offset,
      if (q.trim().isNotEmpty) 'q': q.trim(),
    });
    final map = Map<String, dynamic>.from(body as Map);
    final items = (map['items'] as List? ?? const []).map(_parse).toList();
    return AdminProductPage(
        items: items, total: (map['total'] as num?)?.toInt() ?? items.length);
  }

  Future<AdminProduct> get(String id) async =>
      _parse(await _client.get('/api/staff/products/$id'));

  Future<AdminProduct> create(ProductInput input) async =>
      _parse(await _client.post('/api/staff/products', body: input.toJson()));

  Future<AdminProduct> update(String id, ProductInput input) async => _parse(
      await _client.put('/api/staff/products/$id', body: input.toJson()));

  Future<AdminProduct> setActive(String id, bool active) async =>
      _parse(await _client
          .patch('/api/staff/products/$id/active', body: {'isActive': active}));

  /// Throws [ConflictFailure] (409 `product_in_orders`) when the product is in
  /// an order (Req 20.9).
  Future<void> delete(String id) async {
    await _client.delete('/api/staff/products/$id');
  }

  Future<void> uploadImage(String id, String name, Uint8List bytes) async {
    await _client.postMultipart(
      '/api/staff/products/$id/images',
      files: [http.MultipartFile.fromBytes('image', bytes, filename: name)],
    );
  }
}
