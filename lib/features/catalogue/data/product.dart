/// A catalogue product. Accepts both the new API shape (`priceSen`, category
/// object, `images`) and the prototype/bundled shape (`demoPriceSen`,
/// category string, `imageUrl`).
class Product {
  const Product({
    required this.id,
    required this.name,
    required this.category,
    required this.description,
    required this.imageUrl,
    required this.productUrl,
    required this.priceSen,
  });

  final String id;
  final String name;
  final String category;
  final String description;
  final String imageUrl;
  final String productUrl;

  /// Price in integer sen.
  final int priceSen;

  factory Product.fromJson(Map<String, dynamic> json) {
    final cat = json['category'];
    final images = json['images'];
    var image = json['imageUrl'] as String? ?? '';
    if (image.isEmpty && images is List && images.isNotEmpty) {
      final first = images.first;
      if (first is Map && first['url'] is String) image = first['url'] as String;
    }
    return Product(
      id: json['id'].toString(),
      name: json['name'] as String,
      category: cat is Map ? (cat['name'] as String? ?? '') : (cat as String? ?? ''),
      description: json['description'] as String? ?? '',
      imageUrl: image,
      productUrl: json['productUrl'] as String? ?? '',
      priceSen: ((json['priceSen'] ?? json['demoPriceSen']) as num?)?.toInt() ?? 0,
    );
  }
}
