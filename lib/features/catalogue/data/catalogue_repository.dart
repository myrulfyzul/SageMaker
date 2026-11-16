import '../../../core/network/api_client.dart';
import 'catalogue_models.dart';

const shopPageSize = 20;

/// Home sections show an error within 10 seconds (Req 8.8).
const homeSectionTimeout = Duration(seconds: 10);

/// Server catalogue and Home section reads. Image URLs are made absolute.
class CatalogueRepository {
  CatalogueRepository(this.client);
  final ApiClient client;

  Future<ProductPage> listProducts(ShopQuery query,
      {int limit = shopPageSize, int offset = 0}) async {
    final body = await client.get('/api/products', query: {
      'limit': limit,
      'offset': offset,
      if (query.q.isNotEmpty) 'q': query.q,
      if (query.category != null) 'category': query.category,
      if (query.sort != null) 'sort': query.sort,
    });
    final map = Map<String, dynamic>.from(body as Map);
    return ProductPage(
      items: _parse(map['items'] as List? ?? const []),
      total: (map['total'] as num?)?.toInt() ?? 0,
    );
  }

  Future<CatalogueProduct> getProduct(String id) async {
    final body = await client.get('/api/products/${Uri.encodeComponent(id)}');
    return _parseOne(Map<String, dynamic>.from(body as Map));
  }

  Future<List<CategoryRef>> categories() async {
    final body = await client.get('/api/categories');
    return (body as List)
        .map((c) => CategoryRef.fromJson(Map<String, dynamic>.from(c as Map)))
        .toList();
  }

  Future<List<CatalogueProduct>> bestSellers() => _home('best-sellers');
  Future<List<CatalogueProduct>> newArrivals() => _home('new-arrivals');
  Future<List<CatalogueProduct>> recommendations() => _home('recommendations');

  Future<List<CatalogueProduct>> _home(String section) async {
    final body =
        await client.get('/api/home/$section', timeout: homeSectionTimeout);
    return _parse(body as List? ?? const []);
  }

  List<CatalogueProduct> _parse(List<dynamic> items) =>
      items.map((i) => _parseOne(Map<String, dynamic>.from(i as Map))).toList();

  CatalogueProduct _parseOne(Map<String, dynamic> json) {
    final p = CatalogueProduct.fromJson(json);
    return CatalogueProduct(
      id: p.id,
      name: p.name,
      description: p.description,
      category: p.category,
      priceSen: p.priceSen,
      isDemo: p.isDemo,
      imageUrls: p.imageUrls.map(absoluteUrl).toList(),
      variations: p.variations,
      stockLevel: p.stockLevel,
      stockQuantity: p.stockQuantity,
      artisanName: p.artisanName,
    );
  }

  String absoluteUrl(String url) =>
      url.startsWith('/') ? '${client.baseUrl}$url' : url;
}
