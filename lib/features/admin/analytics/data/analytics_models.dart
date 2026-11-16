import '../../../../core/network/api_client.dart';

int _int(dynamic v) => v is num ? v.toInt() : 0;

/// `GET /api/staff/analytics/dashboard` KPIs (Req 19.2). Money is integer sen.
class DashboardKpis {
  const DashboardKpis({
    this.totalRevenueSen = 0,
    this.orderCount = 0,
    this.pendingOrders = 0,
    this.aovSen = 0,
    this.lowStockCount = 0,
    this.openProductionJobs = 0,
    this.shippedOrderCount = 0,
  });

  final int totalRevenueSen;
  final int orderCount;
  final int pendingOrders;
  final int aovSen;
  final int lowStockCount;
  final int openProductionJobs;
  final int shippedOrderCount;

  factory DashboardKpis.fromJson(Map<String, dynamic> j) => DashboardKpis(
        totalRevenueSen: _int(j['totalRevenueSen']),
        orderCount: _int(j['orderCount']),
        pendingOrders: _int(j['pendingOrders']),
        aovSen: _int(j['aovSen']),
        lowStockCount: _int(j['lowStockCount']),
        openProductionJobs: _int(j['openProductionJobs']),
        shippedOrderCount: _int(j['shippedOrderCount']),
      );
}

/// Revenue and order count of one calendar month (`YYYY-MM`).
class MonthSales {
  const MonthSales(this.month, this.revenueSen, this.orderCount);
  final String month;
  final int revenueSen;
  final int orderCount;

  factory MonthSales.fromJson(Map<String, dynamic> j) => MonthSales(
      (j['month'] ?? '').toString(),
      _int(j['revenueSen']),
      _int(j['orderCount']));
}

class ProductUnits {
  const ProductUnits(this.productId, this.name, this.units);
  final String productId;
  final String name;
  final int units;

  factory ProductUnits.fromJson(Map<String, dynamic> j) => ProductUnits(
      (j['productId'] ?? '').toString(),
      (j['name'] ?? '').toString(),
      _int(j['units']));
}

class CategoryUnits {
  const CategoryUnits(this.category, this.units);
  final String category;
  final int units;

  factory CategoryUnits.fromJson(Map<String, dynamic> j) =>
      CategoryUnits((j['category'] ?? '').toString(), _int(j['units']));
}

List<T> _list<T>(dynamic v, T Function(Map<String, dynamic>) f) => [
      if (v is List)
        for (final e in v)
          if (e is Map) f(Map<String, dynamic>.from(e)),
    ];

class DashboardData {
  const DashboardData({
    this.kpis = const DashboardKpis(),
    this.salesByMonth = const [],
    this.ordersByStatus = const {},
    this.bestSellers = const [],
    this.inventoryByCategory = const [],
  });

  final DashboardKpis kpis;
  final List<MonthSales> salesByMonth;
  final Map<String, int> ordersByStatus;
  final List<ProductUnits> bestSellers;
  final List<CategoryUnits> inventoryByCategory;

  factory DashboardData.fromJson(Map<String, dynamic> j) => DashboardData(
        kpis: DashboardKpis.fromJson(
            Map<String, dynamic>.from((j['kpis'] as Map?) ?? const {})),
        salesByMonth: _list(j['salesByMonth'], MonthSales.fromJson),
        ordersByStatus: {
          if (j['ordersByStatus'] is Map)
            for (final e in (j['ordersByStatus'] as Map).entries)
              e.key.toString(): _int(e.value),
        },
        bestSellers: _list(j['bestSellers'], ProductUnits.fromJson),
        inventoryByCategory:
            _list(j['inventoryByCategory'], CategoryUnits.fromJson),
      );

  bool get salesEmpty => salesByMonth.every((m) => m.revenueSen == 0);
  bool get statusEmpty => ordersByStatus.values.every((v) => v == 0);
  bool get inventoryEmpty => inventoryByCategory.every((c) => c.units == 0);

  /// True when any data exists, so the Demo_Label is shown (Req 19.7).
  bool get hasData =>
      kpis.orderCount > 0 ||
      !inventoryEmpty ||
      kpis.openProductionJobs > 0 ||
      bestSellers.isNotEmpty;
}

/// `GET /api/staff/analytics/sales?start&end` (Req 26).
class SalesReport {
  const SalesReport({
    this.totalRevenueSen = 0,
    this.orderCount = 0,
    this.aovSen = 0,
    this.monthly = const [],
    this.topProducts = const [],
    this.bottomProducts = const [],
  });

  final int totalRevenueSen;
  final int orderCount;
  final int aovSen;
  final List<MonthSales> monthly;
  final List<ProductUnits> topProducts;
  final List<ProductUnits> bottomProducts;

  factory SalesReport.fromJson(Map<String, dynamic> j) => SalesReport(
        totalRevenueSen: _int(j['totalRevenueSen']),
        orderCount: _int(j['orderCount']),
        aovSen: _int(j['aovSen']),
        monthly: _list(j['monthly'], MonthSales.fromJson),
        topProducts: _list(j['topProducts'], ProductUnits.fromJson),
        bottomProducts: _list(j['bottomProducts'], ProductUnits.fromJson),
      );

  bool get monthlyEmpty => monthly.every((m) => m.revenueSen == 0);
}

const maxRangeMonths = 24;

/// Local range check (Req 26.4, 26.6). Returns an error message or null.
String? validateRange(DateTime start, DateTime end) {
  final s = DateTime(start.year, start.month, start.day);
  final e = DateTime(end.year, end.month, end.day);
  if (s.isAfter(e)) return 'The start date must not be after the end date';
  final months = (e.year - s.year) * 12 + e.month - s.month + 1;
  if (months > maxRangeMonths) {
    return 'The range must not exceed $maxRangeMonths months';
  }
  return null;
}

String isoDate(DateTime d) =>
    '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

const analyticsTimeout = Duration(seconds: 10);

class AnalyticsRepository {
  AnalyticsRepository(this._client);
  final ApiClient _client;

  Future<DashboardData> dashboard() async {
    final body = await _client.get('/api/staff/analytics/dashboard',
        timeout: analyticsTimeout);
    return DashboardData.fromJson(Map<String, dynamic>.from(body as Map));
  }

  Future<SalesReport> sales(DateTime start, DateTime end) async {
    final body = await _client.get('/api/staff/analytics/sales',
        query: {'start': isoDate(start), 'end': isoDate(end)},
        timeout: analyticsTimeout);
    return SalesReport.fromJson(Map<String, dynamic>.from(body as Map));
  }
}
