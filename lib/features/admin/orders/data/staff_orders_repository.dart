import '../../../../core/network/api_client.dart';
import '../../../orders/data/order_models.dart';

const staffOrdersPageSize = 20;

/// Fulfilment statuses accepted by the list filter (Req 22.4).
const staffOrderStatuses = [
  'placed',
  'confirmed',
  'preparing',
  'shipped',
  'delivered',
  'cancelled',
  'payment_failed',
];

/// A row of the staff Orders list. Legacy `packing` reads as `preparing`
/// (Req 22.13).
class StaffOrderSummary {
  const StaffOrderSummary({
    required this.id,
    required this.status,
    required this.customerName,
    required this.totalSen,
    required this.itemCount,
    this.paymentStatus = '',
    this.shippingReference,
    this.createdAt,
  });

  factory StaffOrderSummary.fromJson(Map<String, dynamic> j) =>
      StaffOrderSummary(
        id: (j['id'] ?? '').toString(),
        status: normaliseOrderStatus((j['status'] ?? '').toString()),
        customerName: (j['customerName'] ?? '').toString(),
        totalSen: j['totalSen'] is num ? (j['totalSen'] as num).toInt() : 0,
        itemCount: j['itemCount'] is num ? (j['itemCount'] as num).toInt() : 0,
        paymentStatus: (j['paymentStatus'] ?? '').toString(),
        shippingReference: j['shippingReference'] is String &&
                (j['shippingReference'] as String).isNotEmpty
            ? j['shippingReference'] as String
            : null,
        createdAt:
            DateTime.tryParse((j['createdAt'] ?? '').toString())?.toLocal(),
      );

  final String id;
  final String status;
  final String customerName;
  final int totalSen;
  final int itemCount;
  final String paymentStatus;
  final String? shippingReference;
  final DateTime? createdAt;
}

class StaffOrderPage {
  const StaffOrderPage({required this.items, required this.hasMore});

  factory StaffOrderPage.fromJson(Map<String, dynamic> j) => StaffOrderPage(
        items: [
          for (final o in (j['items'] as List? ?? const []))
            StaffOrderSummary.fromJson(Map<String, dynamic>.from(o as Map)),
        ],
        hasMore: j['hasMore'] == true,
      );

  final List<StaffOrderSummary> items;
  final bool hasMore;
}

/// The next forward status for [status], or null when there is none
/// (Req 22.6).
String? nextStaffStatus(String status) {
  switch (normaliseOrderStatus(status)) {
    case 'placed':
      return 'confirmed';
    case 'confirmed':
      return 'preparing';
    case 'preparing':
      return 'shipped';
    case 'shipped':
      return 'delivered';
    default:
      return null;
  }
}

/// Cancellation is allowed from `placed`, `confirmed` and `preparing`.
bool canCancelStaffOrder(String status) =>
    const {'placed', 'confirmed', 'preparing'}
        .contains(normaliseOrderStatus(status));

/// Shipping reference rule (Req 22.8, 22.9): 3 to 80 characters.
String? validateShippingReference(String? value) {
  final n = (value ?? '').trim().length;
  return n >= 3 && n <= 80 ? null : 'Enter 3 to 80 characters';
}

/// Cancel reason rule (Req 22.11): 3 to 500 characters.
String? validateCancelReason(String? value) {
  final n = (value ?? '').trim().length;
  return n >= 3 && n <= 500 ? null : 'Enter 3 to 500 characters';
}

/// `GET /api/staff/orders`, `GET /api/staff/orders/{id}` and
/// `POST /api/staff/orders/{id}/status`.
class StaffOrdersRepository {
  StaffOrdersRepository(this._client);

  final ApiClient _client;

  Future<StaffOrderPage> list({
    String? status,
    String? query,
    int offset = 0,
    int limit = staffOrdersPageSize,
  }) async {
    final q = query?.trim();
    final body = await _client.get('/api/staff/orders', query: {
      'limit': limit,
      'offset': offset,
      if (status != null && status.isNotEmpty) 'status': status,
      if (q != null && q.isNotEmpty) 'q': q,
    });
    return StaffOrderPage.fromJson(Map<String, dynamic>.from(body as Map));
  }

  Future<OrderDetail> get(String id) async {
    final body =
        await _client.get('/api/staff/orders/${Uri.encodeComponent(id)}');
    return OrderDetail.fromJson(Map<String, dynamic>.from(body as Map));
  }

  Future<OrderDetail> changeStatus(
    String id,
    String status, {
    String? shippingReference,
    String? reason,
  }) async {
    final body = await _client
        .post('/api/staff/orders/${Uri.encodeComponent(id)}/status', body: {
      'status': status,
      if (shippingReference != null)
        'shipping_reference': shippingReference.trim(),
      if (reason != null) 'reason': reason.trim(),
    });
    return OrderDetail.fromJson(Map<String, dynamic>.from(body as Map));
  }
}
