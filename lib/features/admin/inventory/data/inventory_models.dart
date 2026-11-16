/// Models for `/api/staff/inventory` (Req 21).
library;

int? _int(dynamic v) => v is num ? v.toInt() : (v is String ? int.tryParse(v) : null);

class StockItem {
  const StockItem({
    required this.productId,
    required this.name,
    required this.quantity,
    required this.threshold,
    required this.lowStock,
  });

  final String productId;
  final String name;
  final int quantity;
  final int threshold;

  /// True when stock is at or below the threshold (Req 21.1).
  final bool lowStock;

  factory StockItem.fromJson(Map<String, dynamic> json) {
    final quantity = _int(json['quantity'] ?? json['stock']) ?? 0;
    final threshold =
        _int(json['lowStockThreshold'] ?? json['threshold']) ?? 0;
    final flag = json['lowStock'] ?? json['isLowStock'] ?? json['low_stock'];
    return StockItem(
      productId: (json['productId'] ?? json['id']).toString(),
      name: (json['name'] ?? json['productName'] ?? '').toString(),
      quantity: quantity,
      threshold: threshold,
      lowStock: flag is bool ? flag : quantity <= threshold,
    );
  }
}

class StockAdjustment {
  const StockAdjustment({
    required this.delta,
    required this.reason,
    required this.actor,
    required this.createdAt,
  });

  final int delta;
  final String reason;
  final String actor;
  final String createdAt;

  factory StockAdjustment.fromJson(Map<String, dynamic> json) {
    final actor = json['actor'];
    return StockAdjustment(
      delta: _int(json['delta']) ?? 0,
      reason: json['reason']?.toString() ?? '',
      actor: actor is Map
          ? (actor['name'] ?? actor['email'] ?? '').toString()
          : (actor ?? json['actorName'] ?? '').toString(),
      createdAt: json['createdAt']?.toString() ?? '',
    );
  }
}
