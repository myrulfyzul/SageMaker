import '../../../../core/network/api_client.dart';

/// Staff view of a custom order (`/api/staff/custom-orders`, Req 25).
class StaffCustomOrder {
  const StaffCustomOrder({
    required this.id,
    required this.productType,
    required this.description,
    required this.quantity,
    required this.preferredDate,
    required this.status,
    this.estimatedPriceSen,
    this.rejectReason,
    this.artisanId,
    this.productionLabel,
    this.productionProgressPercent,
    this.isDemo = false,
  });

  factory StaffCustomOrder.fromJson(Map<String, dynamic> j) =>
      StaffCustomOrder(
        id: (j['id'] as num).toInt(),
        productType: (j['productType'] ?? '').toString(),
        description: (j['description'] ?? '').toString(),
        quantity: (j['quantity'] as num? ?? 0).toInt(),
        preferredDate: (j['preferredDate'] ?? '').toString(),
        status: (j['status'] ?? 'submitted').toString(),
        estimatedPriceSen: (j['estimatedPriceSen'] as num?)?.toInt(),
        rejectReason: j['rejectReason'] as String?,
        artisanId: (j['artisanId'] as num?)?.toInt(),
        productionLabel: j['productionLabel'] as String?,
        productionProgressPercent:
            (j['productionProgressPercent'] as num?)?.toInt(),
        isDemo: j['isDemo'] == true,
      );

  final int id;
  final String productType;
  final String description;
  final int quantity;
  final String preferredDate;
  final String status;
  final int? estimatedPriceSen;
  final String? rejectReason;
  final int? artisanId;
  final String? productionLabel;
  final int? productionProgressPercent;
  final bool isDemo;

  /// Actions the state machine allows (Req 25.10).
  bool get canAccept => status == 'submitted';
  bool get canReject => status == 'submitted';
  bool get canAssign => status == 'accepted' && artisanId == null;
  String? get nextStatus => switch (status) {
        'accepted' => 'in_progress',
        'in_progress' => 'completed',
        _ => null,
      };
}

const customOrderStatuses = [
  'submitted',
  'accepted',
  'rejected',
  'in_progress',
  'completed'
];

class StaffCustomOrderPage {
  const StaffCustomOrderPage(this.items, this.total);
  final List<StaffCustomOrder> items;
  final int total;
  bool get hasMore => items.length < total;
}

/// An artisan that can be assigned.
class AssignableArtisan {
  const AssignableArtisan(this.id, this.name, this.specialisation);
  final int id;
  final String name;
  final String specialisation;
}

/// Reason must be 5 to 500 characters after trimming (Req 25.6).
String? validateRejectReason(String? v) {
  final n = (v ?? '').trim().length;
  if (n < 5 || n > 500) return 'Reason must be 5 to 500 characters';
  return null;
}

class StaffCustomOrdersRepository {
  StaffCustomOrdersRepository(this._client);
  final ApiClient _client;

  static const pageSize = 20;

  Future<StaffCustomOrderPage> list(
      {String? status, int offset = 0}) async {
    final body = await _client.get('/api/staff/custom-orders', query: {
      'limit': pageSize,
      'offset': offset,
      if (status != null) 'status': status,
    });
    final m = Map<String, dynamic>.from(body as Map);
    final items = [
      for (final e in (m['items'] as List? ?? const []))
        StaffCustomOrder.fromJson(Map<String, dynamic>.from(e as Map))
    ];
    return StaffCustomOrderPage(items, (m['total'] as num?)?.toInt() ?? items.length);
  }

  Future<void> accept(int id, int priceSen) => _client.post(
      '/api/staff/custom-orders/$id/accept',
      body: {'estimatedPriceSen': priceSen});

  Future<void> reject(int id, String reason) => _client.post(
      '/api/staff/custom-orders/$id/reject',
      body: {'reason': reason.trim()});

  Future<void> assign(int id, int artisanId) => _client.post(
      '/api/staff/custom-orders/$id/assign-artisan',
      body: {'artisanId': artisanId});

  Future<void> setStatus(int id, String status) => _client
      .post('/api/staff/custom-orders/$id/status', body: {'status': status});

  Future<List<AssignableArtisan>> activeArtisans() async {
    final body =
        await _client.get('/api/staff/artisans', query: {'limit': 100});
    final rows = body is Map ? (body['items'] as List? ?? const []) : body as List;
    return [
      for (final r in rows)
        if ((r as Map)['isActive'] != false)
          AssignableArtisan((r['id'] as num).toInt(), (r['name'] ?? '').toString(),
              (r['specialisation'] ?? '').toString())
    ];
  }
}
