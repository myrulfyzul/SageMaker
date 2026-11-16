import 'dart:convert';

import '../../../core/network/api_client.dart';
import 'product.dart';

const bundledProductsAsset = 'assets/products.json';
const serverProductsTimeout = Duration(seconds: 3);

/// Server-first catalogue with a bundled-JSON fallback (offline browsing only).
class ProductRepository {
  ProductRepository({required this.client, required this.loadAsset});

  final ApiClient client;
  final Future<String> Function(String key) loadAsset;

  Future<List<Product>> loadProducts() async {
    try {
      final body = await client.get('/api/products',
          query: {'limit': 50}, timeout: serverProductsTimeout);
      final list = body is Map ? body['items'] : body;
      if (list is List) return parse(list);
    } catch (_) {
      // Browsing stays possible when the optional server is off.
    }
    final raw = await loadAsset(bundledProductsAsset);
    return parse(jsonDecode(raw) as List<dynamic>);
  }

  static List<Product> parse(List<dynamic> items) => items
      .map((item) => Product.fromJson(Map<String, dynamic>.from(item as Map)))
      .toList();
}
