/// Server order DTOs for My Orders and order tracking (Req 15).
library;

int _int(Object? v) => v is num ? v.toInt() : 0;
String? _str(Object? v) => v is String && v.isNotEmpty ? v : null;

/// Reads a legacy `packing` status as `preparing` (Req 14.6).
String normaliseOrderStatus(String status) =>
    status == 'packing' ? 'preparing' : status;

class OrderLineItem {
  const OrderLineItem({
    required this.name,
    required this.quantity,
    required this.unitPriceSen,
    required this.lineTotalSen,
    this.variationLabel,
  });

  factory OrderLineItem.fromJson(Map<String, dynamic> j) => OrderLineItem(
        name: (j['name'] ?? '').toString(),
        quantity: _int(j['quantity']),
        unitPriceSen: _int(j['unitPriceSen']),
        lineTotalSen: _int(j['lineTotalSen']),
        variationLabel: _str(j['variationLabel']),
      );

  final String name;
  final int quantity;
  final int unitPriceSen;
  final int lineTotalSen;
  final String? variationLabel;
}

class OrderHistoryEntry {
  const OrderHistoryEntry({required this.status, this.at});

  factory OrderHistoryEntry.fromJson(Map<String, dynamic> j) =>
      OrderHistoryEntry(
        status: normaliseOrderStatus(
            (j['status'] ?? j['newStatus'] ?? '').toString()),
        at: DateTime.tryParse((j['at'] ?? j['createdAt'] ?? '').toString())
            ?.toLocal(),
      );

  final String status;
  final DateTime? at;
}

class OrderDelivery {
  const OrderDelivery({
    required this.name,
    required this.phone,
    required this.email,
    required this.address,
    this.postcode,
    this.state,
    this.notes,
  });

  factory OrderDelivery.fromJson(Map<String, dynamic> j) => OrderDelivery(
        name: (j['name'] ?? '').toString(),
        phone: (j['phone'] ?? '').toString(),
        email: (j['email'] ?? '').toString(),
        address: (j['address'] ?? '').toString(),
        postcode: _str(j['postcode']),
        state: _str(j['state']),
        notes: _str(j['notes']),
      );

  final String name;
  final String phone;
  final String email;
  final String address;
  final String? postcode;
  final String? state;
  final String? notes;
}

/// A row of My Orders.
class OrderSummary {
  const OrderSummary({
    required this.id,
    required this.status,
    required this.paymentStatus,
    required this.paymentMethod,
    required this.totalSen,
    required this.itemCount,
    this.createdAt,
  });

  factory OrderSummary.fromJson(Map<String, dynamic> j) => OrderSummary(
        id: (j['id'] ?? '').toString(),
        status: normaliseOrderStatus((j['status'] ?? '').toString()),
        paymentStatus: (j['paymentStatus'] ?? '').toString(),
        paymentMethod: (j['paymentMethod'] ?? '').toString(),
        totalSen: _int(j['totalSen']),
        itemCount: _int(j['itemCount']),
        createdAt:
            DateTime.tryParse((j['createdAt'] ?? '').toString())?.toLocal(),
      );

  final String id;
  final String status;
  final String paymentStatus;
  final String paymentMethod;
  final int totalSen;
  final int itemCount;
  final DateTime? createdAt;
}

class OrderPage {
  const OrderPage({required this.items, required this.hasMore});

  factory OrderPage.fromJson(Map<String, dynamic> j) => OrderPage(
        items: [
          for (final o in (j['items'] as List? ?? const []))
            OrderSummary.fromJson(Map<String, dynamic>.from(o as Map)),
        ],
        hasMore: j['hasMore'] == true,
      );

  final List<OrderSummary> items;
  final bool hasMore;
}

class OrderDetail {
  const OrderDetail({
    required this.id,
    required this.status,
    required this.paymentStatus,
    required this.paymentMethod,
    required this.lines,
    required this.subtotalSen,
    required this.shippingFeeSen,
    required this.totalSen,
    required this.delivery,
    required this.history,
    this.shippingReference,
    this.productionLabel,
    this.createdAt,
  });

  factory OrderDetail.fromJson(Map<String, dynamic> j) => OrderDetail(
        id: (j['id'] ?? '').toString(),
        status: normaliseOrderStatus((j['status'] ?? '').toString()),
        paymentStatus: (j['paymentStatus'] ?? '').toString(),
        paymentMethod: (j['paymentMethod'] ?? '').toString(),
        lines: [
          for (final l in (j['lines'] as List? ?? const []))
            OrderLineItem.fromJson(Map<String, dynamic>.from(l as Map)),
        ],
        subtotalSen: _int(j['subtotalSen']),
        shippingFeeSen: _int(j['shippingFeeSen']),
        totalSen: _int(j['totalSen']),
        delivery: OrderDelivery.fromJson(j['delivery'] is Map
            ? Map<String, dynamic>.from(j['delivery'] as Map)
            : const {}),
        history: [
          for (final h in (j['history'] as List? ?? const []))
            OrderHistoryEntry.fromJson(Map<String, dynamic>.from(h as Map)),
        ],
        shippingReference: _str(j['shippingReference']),
        productionLabel: _str(j['productionLabel']),
        createdAt:
            DateTime.tryParse((j['createdAt'] ?? '').toString())?.toLocal(),
      );

  final String id;
  final String status;
  final String paymentStatus;
  final String paymentMethod;
  final List<OrderLineItem> lines;
  final int subtotalSen;
  final int shippingFeeSen;
  final int totalSen;
  final OrderDelivery delivery;
  final List<OrderHistoryEntry> history;
  final String? shippingReference;

  /// Read-only production status, separate from the timeline (Req 15.10).
  final String? productionLabel;
  final DateTime? createdAt;
}

/// One row of the tracking timeline.
class TimelineStep {
  const TimelineStep({
    required this.status,
    required this.label,
    required this.reached,
    this.at,
    this.terminal = false,
  });

  final String status;
  final String label;
  final bool reached;
  final DateTime? at;

  /// The cancelled or payment-failed state shown in place of unreached steps.
  final bool terminal;
}

const timelineStatuses = [
  'placed',
  'confirmed',
  'preparing',
  'shipped',
  'delivered',
];

const _labels = {
  'placed': 'Placed',
  'confirmed': 'Confirmed',
  'preparing': 'Preparing',
  'shipped': 'Shipped',
  'delivered': 'Delivered',
  'cancelled': 'Cancelled',
  'payment_failed': 'Payment failed',
};

String orderStatusLabel(String status) =>
    _labels[normaliseOrderStatus(status)] ?? status;

/// Builds the timeline from the history entries (Req 15.6, 15.7). Steps with
/// a history entry are reached and carry its time; the others are not yet
/// reached. For a `cancelled` or `payment_failed` order the reached steps are
/// kept and the terminal state with its timestamp replaces the unreached ones.
List<TimelineStep> buildTimeline(
    String status, List<OrderHistoryEntry> history) {
  DateTime? firstAt(String s) {
    for (final h in history) {
      if (h.status == s) return h.at;
    }
    return null;
  }

  bool has(String s) => history.any((h) => h.status == s);

  final current = normaliseOrderStatus(status);
  final steps = <TimelineStep>[
    for (final s in timelineStatuses)
      TimelineStep(
          status: s, label: _labels[s]!, reached: has(s), at: firstAt(s)),
  ];
  if (current != 'cancelled' && current != 'payment_failed') return steps;

  DateTime? terminalAt;
  for (final h in history) {
    if (h.status == current) terminalAt = h.at;
  }
  return [
    ...steps.where((s) => s.reached),
    TimelineStep(
        status: current,
        label: _labels[current]!,
        reached: true,
        at: terminalAt,
        terminal: true),
  ];
}

/// `2 Jun 2025, 14:05` in the device's local time.
String formatLocalDateTime(DateTime t) {
  const months = [
    'Jan',
    'Feb',
    'Mar',
    'Apr',
    'May',
    'Jun',
    'Jul',
    'Aug',
    'Sep',
    'Oct',
    'Nov',
    'Dec',
  ];
  final l = t.toLocal();
  String two(int n) => n.toString().padLeft(2, '0');
  return '${l.day} ${months[l.month - 1]} ${l.year}, ${two(l.hour)}:${two(l.minute)}';
}

String paymentMethodLabel(String m) {
  switch (m) {
    case 'card':
      return 'Card (demo)';
    case 'online_banking':
      return 'Online banking (demo)';
    case 'ewallet':
      return 'E-wallet (demo)';
    case 'cod':
      return 'Cash on delivery (demo)';
    default:
      return m.isEmpty ? 'Not set' : m.replaceAll('_', ' ');
  }
}

String paymentStatusLabel(String s) {
  switch (s) {
    case 'paid':
      return 'Paid (simulated)';
    case 'pending_cod':
      return 'Pay on delivery';
    case 'failed':
      return 'Failed';
    case 'demo_simulated_not_charged':
      return 'Simulated, not charged';
    default:
      return s.isEmpty ? 'Unknown' : s.replaceAll('_', ' ');
  }
}
