/// Models for `/api/staff/products` (Req 20).
library;

import '../../../catalogue/data/catalogue_models.dart';

int? _int(dynamic v) => v is num ? v.toInt() : (v is String ? int.tryParse(v) : null);

/// A product as staff see it, including inactive ones.
class AdminProduct {
  const AdminProduct({
    required this.id,
    required this.name,
    required this.description,
    required this.categoryId,
    required this.categoryName,
    required this.priceSen,
    required this.stock,
    required this.lowStockThreshold,
    required this.isActive,
    required this.imageUrls,
  });

  final String id;
  final String name;
  final String description;
  final int? categoryId;
  final String categoryName;
  final int priceSen;
  final int stock;
  final int lowStockThreshold;
  final bool isActive;
  final List<String> imageUrls;

  String? get firstImage => imageUrls.isEmpty ? null : imageUrls.first;

  factory AdminProduct.fromJson(Map<String, dynamic> json) {
    final stockRaw = json['stock'];
    final stockMap = stockRaw is Map ? stockRaw : const {};
    final category = json['category'];
    return AdminProduct(
      id: json['id'].toString(),
      name: json['name'] as String? ?? '',
      description: json['description'] as String? ?? '',
      categoryId: category is Map
          ? _int(category['id'])
          : _int(json['categoryId'] ?? category),
      categoryName: category is Map ? (category['name'] as String? ?? '') : '',
      priceSen: _int(json['priceSen'] ?? json['demoPriceSen']) ?? 0,
      stock: _int(stockRaw is num ? stockRaw : stockMap['quantity']) ??
          _int(json['stockQuantity']) ??
          0,
      lowStockThreshold: _int(json['lowStockThreshold'] ??
              stockMap['lowStockThreshold'] ??
              stockMap['threshold']) ??
          0,
      isActive: json['isActive'] as bool? ?? json['active'] as bool? ?? true,
      imageUrls: (json['images'] as List? ?? const [])
          .map((i) => i is Map ? i['url'] : i)
          .whereType<String>()
          .where((u) => u.isNotEmpty)
          .toList(),
    );
  }
}

class AdminProductPage {
  const AdminProductPage({required this.items, required this.total});
  final List<AdminProduct> items;
  final int total;
}

/// Values of the create and edit form, in server units.
class ProductInput {
  const ProductInput({
    required this.name,
    required this.description,
    required this.categoryId,
    required this.priceSen,
    required this.stock,
    required this.lowStockThreshold,
  });

  final String name;
  final String description;
  final int categoryId;
  final int priceSen;
  final int stock;
  final int lowStockThreshold;

  Map<String, Object?> toJson() => {
        'name': name.trim(),
        'description': description.trim(),
        'categoryId': categoryId,
        'priceSen': priceSen,
        'stock': stock,
        'lowStockThreshold': lowStockThreshold,
      };
}

/// Category choices for the form reuse the catalogue's [CategoryRef].
typedef ProductCategory = CategoryRef;
