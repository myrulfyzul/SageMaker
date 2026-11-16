/// Models for the checkout, payment and confirmation flow (Req 12, 13).
library;

const paymentMethods = ['card', 'fpx', 'ewallet', 'cod'];
const simulatedOutcomes = ['success', 'failed', 'cancelled'];

String paymentMethodLabel(String method) => switch (method) {
      'card' => 'Card (demo)',
      'fpx' => 'FPX online banking (demo)',
      'ewallet' => 'E-wallet (demo)',
      'cod' => 'Cash on delivery',
      _ => method,
    };

String outcomeLabel(String outcome) => switch (outcome) {
      'success' => 'Success',
      'failed' => 'Failed',
      'cancelled' => 'Cancelled',
      _ => outcome,
    };

/// True for methods where the tester picks a simulated outcome (Req 13.2).
bool methodNeedsOutcome(String method) => method != 'cod';

class CartLine {
  const CartLine({
    required this.name,
    required this.variationLabel,
    required this.quantity,
    required this.unitPriceSen,
    required this.lineTotalSen,
    required this.available,
  });

  factory CartLine.fromJson(Map<String, dynamic> j) => CartLine(
        name: (j['name'] as String?) ?? 'Unavailable item',
        variationLabel: j['variationLabel'] as String?,
        quantity: (j['quantity'] as num?)?.toInt() ?? 0,
        unitPriceSen: (j['unitPriceSen'] as num?)?.toInt() ?? 0,
        lineTotalSen: (j['lineTotalSen'] as num?)?.toInt() ?? 0,
        available: j['available'] as bool? ?? true,
      );

  final String name;
  final String? variationLabel;
  final int quantity;
  final int unitPriceSen;
  final int lineTotalSen;
  final bool available;
}

/// Server cart as returned by `GET /api/cart`.
class CheckoutCart {
  const CheckoutCart({
    required this.lines,
    required this.subtotalSen,
    required this.deliveryFeeSen,
    required this.grandTotalSen,
  });

  factory CheckoutCart.fromJson(Map<String, dynamic> j) => CheckoutCart(
        lines: [
          for (final l in (j['lines'] as List? ?? const []))
            CartLine.fromJson(Map<String, dynamic>.from(l as Map)),
        ],
        subtotalSen: (j['subtotalSen'] as num?)?.toInt() ?? 0,
        deliveryFeeSen: (j['deliveryFeeSen'] as num?)?.toInt() ?? 0,
        grandTotalSen: (j['grandTotalSen'] as num?)?.toInt() ?? 0,
      );

  final List<CartLine> lines;
  final int subtotalSen;
  final int deliveryFeeSen;
  final int grandTotalSen;

  bool get isEmpty => lines.isEmpty;
  bool get hasUnavailable => lines.any((l) => !l.available);
}

/// Delivery fields as typed by the customer. Values are kept on error.
class DeliveryForm {
  const DeliveryForm({
    this.name = '',
    this.phone = '',
    this.email = '',
    this.address = '',
    this.postcode = '',
    this.state = '',
    this.notes = '',
  });

  final String name;
  final String phone;
  final String email;
  final String address;
  final String postcode;
  final String state;
  final String notes;

  DeliveryForm copyWith({
    String? name,
    String? phone,
    String? email,
    String? address,
    String? postcode,
    String? state,
    String? notes,
  }) =>
      DeliveryForm(
        name: name ?? this.name,
        phone: phone ?? this.phone,
        email: email ?? this.email,
        address: address ?? this.address,
        postcode: postcode ?? this.postcode,
        state: state ?? this.state,
        notes: notes ?? this.notes,
      );

  Map<String, dynamic> toJson() => {
        'name': name.trim(),
        'phone': phone.trim(),
        'email': email.trim(),
        'address': address.trim(),
        'postcode': postcode.trim(),
        'state': state.trim(),
        if (notes.trim().isNotEmpty) 'notes': notes.trim(),
      };
}

/// A saved address from `GET /api/me/addresses`.
class SavedAddress {
  const SavedAddress({
    required this.recipientName,
    required this.phone,
    required this.line1,
    this.line2,
    required this.postcode,
    required this.state,
    required this.isDefault,
  });

  factory SavedAddress.fromJson(Map<String, dynamic> j) => SavedAddress(
        recipientName: (j['recipientName'] as String?) ?? '',
        phone: (j['phone'] as String?) ?? '',
        line1: (j['line1'] as String?) ?? '',
        line2: j['line2'] as String?,
        postcode: (j['postcode'] as String?) ?? '',
        state: (j['state'] as String?) ?? '',
        isDefault: j['isDefault'] as bool? ?? false,
      );

  final String recipientName;
  final String phone;
  final String line1;
  final String? line2;
  final String postcode;
  final String state;
  final bool isDefault;

  /// Prefill for name, phone, address, postcode and state (Req 12.5).
  DeliveryForm toForm({String email = ''}) => DeliveryForm(
        name: recipientName,
        phone: phone,
        email: email,
        address: [line1, if (line2 != null && line2!.trim().isNotEmpty) line2!]
            .join(', '),
        postcode: postcode,
        state: state,
      );
}

class OrderLine {
  const OrderLine(
      {required this.name,
      required this.quantity,
      required this.lineTotalSen,
      this.variationLabel});

  factory OrderLine.fromJson(Map<String, dynamic> j) => OrderLine(
        name: (j['name'] as String?) ?? '',
        variationLabel: j['variationLabel'] as String?,
        quantity: (j['quantity'] as num?)?.toInt() ?? 0,
        lineTotalSen: (j['lineTotalSen'] as num?)?.toInt() ?? 0,
      );

  final String name;
  final String? variationLabel;
  final int quantity;
  final int lineTotalSen;
}

/// The part of an order the checkout, payment and confirmation screens use.
class PlacedOrder {
  const PlacedOrder({
    required this.id,
    required this.status,
    required this.paymentStatus,
    required this.paymentMethod,
    required this.totalSen,
    required this.lines,
  });

  factory PlacedOrder.fromJson(Map<String, dynamic> j) => PlacedOrder(
        id: j['id'] as String,
        status: (j['status'] as String?) ?? '',
        paymentStatus: (j['paymentStatus'] as String?) ?? '',
        paymentMethod: (j['paymentMethod'] as String?) ?? '',
        totalSen: (j['totalSen'] as num?)?.toInt() ?? 0,
        lines: [
          for (final l in (j['lines'] as List? ?? const []))
            OrderLine.fromJson(Map<String, dynamic>.from(l as Map)),
        ],
      );

  final String id;
  final String status;
  final String paymentStatus;
  final String paymentMethod;
  final int totalSen;
  final List<OrderLine> lines;

  bool get canRetryPayment => status == 'payment_failed';
}

/// One item reported short by a 409 (Req 13.12, 14.3).
class StockShortage {
  const StockShortage(
      {required this.productId,
      required this.requested,
      required this.available});

  factory StockShortage.fromJson(Map<String, dynamic> j) => StockShortage(
        productId: (j['productId'] ?? '').toString(),
        requested: (j['requested'] as num?)?.toInt(),
        available: (j['available'] as num?)?.toInt() ?? 0,
      );

  final String productId;
  final int? requested;
  final int available;

  String get text => requested == null
      ? '$productId: $available available'
      : '$productId: $requested requested, $available available';
}
