/// Custom order as returned by `/api/custom-orders` (Req 16).
class CustomOrder {
  const CustomOrder({
    required this.id,
    required this.productType,
    required this.description,
    required this.quantity,
    required this.preferredDate,
    required this.status,
    this.estimatedPriceSen,
    this.rejectReason,
    this.imageUrls = const [],
    this.createdAt,
  });

  final int id;
  final String productType;
  final String description;
  final int quantity;
  final String preferredDate;
  final String status;
  final int? estimatedPriceSen;
  final String? rejectReason;
  final List<String> imageUrls;
  final String? createdAt;

  factory CustomOrder.fromJson(Map<String, dynamic> j) => CustomOrder(
        id: (j['id'] as num).toInt(),
        productType: (j['productType'] ?? '').toString(),
        description: (j['description'] ?? '').toString(),
        quantity: (j['quantity'] as num? ?? 0).toInt(),
        preferredDate: (j['preferredDate'] ?? '').toString(),
        status: (j['status'] ?? 'submitted').toString(),
        estimatedPriceSen: (j['estimatedPriceSen'] as num?)?.toInt(),
        rejectReason: j['rejectReason'] as String?,
        imageUrls: [
          for (final u in (j['imageUrls'] as List? ?? const [])) u.toString()
        ],
        createdAt: j['createdAt'] as String?,
      );
}

class CustomOrderPage {
  const CustomOrderPage(
      {required this.items, required this.total, required this.offset});

  final List<CustomOrder> items;
  final int total;
  final int offset;

  bool get hasMore => offset + items.length < total;

  factory CustomOrderPage.fromJson(Map<String, dynamic> j) => CustomOrderPage(
        items: [
          for (final e in (j['items'] as List? ?? const []))
            CustomOrder.fromJson(Map<String, dynamic>.from(e as Map))
        ],
        total: (j['total'] as num? ?? 0).toInt(),
        offset: (j['offset'] as num? ?? 0).toInt(),
      );
}

/// Customer-facing label for a custom order status.
String customOrderStatusLabel(String status) => switch (status) {
      'submitted' => 'Submitted',
      'accepted' => 'Accepted',
      'rejected' => 'Rejected',
      'in_progress' => 'In progress',
      'completed' => 'Completed',
      _ => status,
    };
