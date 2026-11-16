/// Models for the server catalogue (`/api/products`, `/api/categories`).
library;

enum StockLevel { inStock, lowStock, outOfStock }

/// Stock status text (Req 9.11): "In stock", "Low stock: N left" or
/// "Out of stock".
String stockStatusText(StockLevel level, int quantity) => switch (level) {
      StockLevel.outOfStock => 'Out of stock',
      StockLevel.lowStock => 'Low stock: $quantity left',
      StockLevel.inStock => 'In stock',
    };

class CategoryRef {
  const CategoryRef({required this.id, required this.slug, required this.name});
  final int id;
  final String slug;
  final String name;

  factory CategoryRef.fromJson(Map<String, dynamic> json) => CategoryRef(
        id: (json['id'] as num).toInt(),
        slug: json['slug'] as String? ?? '',
        name: json['name'] as String? ?? '',
      );
}

class ProductVariation {
  const ProductVariation({
    required this.id,
    required this.label,
    required this.priceSen,
    required this.isActive,
    required this.stockQuantity,
  });
  final int id;
  final String label;
  final int priceSen;
  final bool isActive;
  final int stockQuantity;

  factory ProductVariation.fromJson(Map<String, dynamic> json) =>
      ProductVariation(
        id: (json['id'] as num).toInt(),
        label: json['label'] as String? ?? '',
        priceSen: (json['priceSen'] as num?)?.toInt() ?? 0,
        isActive: json['isActive'] as bool? ?? true,
        stockQuantity: (json['stockQuantity'] as num?)?.toInt() ?? 0,
      );
}

class CatalogueProduct {
  const CatalogueProduct({
    required this.id,
    required this.name,
    required this.description,
    required this.category,
    required this.priceSen,
    required this.isDemo,
    required this.imageUrls,
    required this.variations,
    required this.stockLevel,
    required this.stockQuantity,
    this.artisanName,
  });

  final String id;
  final String name;
  final String description;
  final CategoryRef category;
  final int priceSen;
  final bool isDemo;
  final List<String> imageUrls;
  final List<ProductVariation> variations;
  final StockLevel stockLevel;
  final int stockQuantity;

  /// Public artisan name, present only when an artisan is linked.
  final String? artisanName;

  bool get outOfStock => stockLevel == StockLevel.outOfStock;
  String get stockText => stockStatusText(stockLevel, stockQuantity);
  String? get firstImage => imageUrls.isEmpty ? null : imageUrls.first;

  factory CatalogueProduct.fromJson(Map<String, dynamic> json) {
    final stock = Map<String, dynamic>.from(json['stock'] as Map? ?? {});
    final level = switch (stock['status']) {
      'low_stock' => StockLevel.lowStock,
      'out_of_stock' => StockLevel.outOfStock,
      _ => StockLevel.inStock,
    };
    final artisan = json['artisan'];
    final images = (json['images'] as List? ?? const [])
        .whereType<Map>()
        .map((i) => i['url'])
        .whereType<String>()
        .where((u) => u.isNotEmpty)
        .toList();
    return CatalogueProduct(
      id: json['id'].toString(),
      name: json['name'] as String? ?? '',
      description: json['description'] as String? ?? '',
      category: CategoryRef.fromJson(
          Map<String, dynamic>.from(json['category'] as Map? ?? {'id': 0})),
      priceSen:
          ((json['priceSen'] ?? json['demoPriceSen']) as num?)?.toInt() ?? 0,
      isDemo: json['isDemo'] as bool? ?? true,
      imageUrls: images,
      variations: (json['variations'] as List? ?? const [])
          .map((v) =>
              ProductVariation.fromJson(Map<String, dynamic>.from(v as Map)))
          .toList(),
      stockLevel: level,
      stockQuantity: (stock['quantity'] as num?)?.toInt() ?? 0,
      artisanName: artisan is Map ? artisan['name'] as String? : null,
    );
  }
}

class ProductPage {
  const ProductPage({required this.items, required this.total});
  final List<CatalogueProduct> items;
  final int total;
}

/// Shop query (Req 9.2, 9.4, 9.6). [sort] is `price_asc`, `price_desc` or null.
class ShopQuery {
  const ShopQuery({this.q = '', this.category, this.sort});
  final String q;
  final String? category;
  final String? sort;

  ShopQuery copyWith({String? q, String? category, String? sort,
          bool clearCategory = false, bool clearSort = false}) =>
      ShopQuery(
        q: q ?? this.q,
        category: clearCategory ? null : (category ?? this.category),
        sort: clearSort ? null : (sort ?? this.sort),
      );

  @override
  bool operator ==(Object other) =>
      other is ShopQuery &&
      other.q == q &&
      other.category == category &&
      other.sort == sort;

  @override
  int get hashCode => Object.hash(q, category, sort);
}
