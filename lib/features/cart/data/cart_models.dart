/// Cart models for `/api/cart` (Req 11). All money is integer sen.
library;

/// Key used for a line in the guest cart map: the product id, or
/// `productId#variationId` for a variation.
String cartKey(String productId, int? variationId) =>
    variationId == null ? productId : '$productId#$variationId';

/// Splits a [cartKey] back into product id and variation id.
({String productId, int? variationId}) parseCartKey(String key) {
  final i = key.lastIndexOf('#');
  if (i > 0) {
    final v = int.tryParse(key.substring(i + 1));
    if (v != null) return (productId: key.substring(0, i), variationId: v);
  }
  return (productId: key, variationId: null);
}

class CartLine {
  const CartLine({
    this.id,
    required this.productId,
    this.variationId,
    this.name,
    this.variationLabel,
    this.imageUrl,
    required this.quantity,
    required this.unitPriceSen,
    required this.lineTotalSen,
    required this.available,
    this.availableQuantity = 0,
  });

  /// Server line id; null for guest lines.
  final int? id;
  final String productId;
  final int? variationId;
  final String? name;
  final String? variationLabel;
  final String? imageUrl;
  final int quantity;
  final int unitPriceSen;
  final int lineTotalSen;

  /// False when the product is inactive or out of stock (Req 11.7).
  final bool available;
  final int availableQuantity;

  String get key => cartKey(productId, variationId);

  factory CartLine.fromJson(Map<String, dynamic> j) => CartLine(
        id: (j['id'] as num?)?.toInt(),
        productId: j['productId'].toString(),
        variationId: (j['variationId'] as num?)?.toInt(),
        name: j['name'] as String?,
        variationLabel: j['variationLabel'] as String?,
        imageUrl: j['imageUrl'] as String?,
        quantity: (j['quantity'] as num?)?.toInt() ?? 0,
        unitPriceSen: (j['unitPriceSen'] as num?)?.toInt() ?? 0,
        lineTotalSen: (j['lineTotalSen'] as num?)?.toInt() ?? 0,
        available: j['available'] as bool? ?? false,
        availableQuantity: (j['availableQuantity'] as num?)?.toInt() ?? 0,
      );
}

class CartData {
  const CartData({
    this.lines = const [],
    this.subtotalSen = 0,
    this.deliveryFeeSen = 0,
    this.grandTotalSen = 0,
  });

  final List<CartLine> lines;
  final int subtotalSen;
  final int deliveryFeeSen;
  final int grandTotalSen;

  /// Total units across all lines, for the Cart badge.
  int get itemCount => lines.fold(0, (sum, l) => sum + l.quantity);
  bool get hasAvailableLines => lines.any((l) => l.available);

  /// Totals for [lines]: unavailable lines are excluded from the subtotal and
  /// the delivery fee is 800 sen while at least one line is available.
  factory CartData.fromLines(List<CartLine> lines) {
    final subtotal = lines.where((l) => l.available).fold<int>(
        0, (sum, l) => sum + l.lineTotalSen);
    final fee = lines.any((l) => l.available) ? 800 : 0;
    return CartData(
        lines: lines,
        subtotalSen: subtotal,
        deliveryFeeSen: fee,
        grandTotalSen: subtotal + fee);
  }

  factory CartData.fromJson(Map<String, dynamic> j) => CartData(
        lines: [
          for (final l in (j['lines'] as List? ?? const []))
            CartLine.fromJson(Map<String, dynamic>.from(l as Map)),
        ],
        subtotalSen: (j['subtotalSen'] as num?)?.toInt() ?? 0,
        deliveryFeeSen: (j['deliveryFeeSen'] as num?)?.toInt() ?? 0,
        grandTotalSen: (j['grandTotalSen'] as num?)?.toInt() ?? 0,
      );
}

/// A guest line that the server capped or rejected during the login merge
/// (Req 11.13). [quantity] is the amount that was left out.
class NotMergedItem {
  const NotMergedItem({
    required this.productId,
    this.variationId,
    required this.quantity,
    required this.reason,
    this.name,
  });

  final String productId;
  final int? variationId;
  final int quantity;
  final String reason;
  final String? name;

  String get key => cartKey(productId, variationId);

  String get reasonText => switch (reason) {
        'insufficient_stock' => 'not enough stock',
        'line_limit' => 'limit of 20 per line',
        'unavailable' => 'no longer available',
        _ => 'could not be added',
      };

  NotMergedItem withName(String? n) => NotMergedItem(
      productId: productId,
      variationId: variationId,
      quantity: quantity,
      reason: reason,
      name: n);

  static NotMergedItem? tryParse(dynamic raw) {
    if (raw is! Map || raw['productId'] is! String) return null;
    return NotMergedItem(
      productId: raw['productId'] as String,
      variationId: (raw['variationId'] as num?)?.toInt(),
      quantity: (raw['quantity'] as num?)?.toInt() ?? 0,
      reason: raw['reason']?.toString() ?? '',
    );
  }
}

/// Result of `POST /api/cart/merge`.
class MergeResult {
  const MergeResult(this.cart, this.notMerged);
  final CartData cart;
  final List<NotMergedItem> notMerged;
}
