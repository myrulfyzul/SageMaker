import '../features/auth/data/auth_user.dart';

/// Bottom-bar destinations of the staff shell, in display order (Req 19.1).
enum StaffDestination {
  dashboard('Dashboard', 'dashboard'),
  orders('Orders', 'orders'),
  products('Products', 'products'),
  production('Production', 'production'),
  more('More', 'more');

  const StaffDestination(this.label, this.segment);

  final String label;
  final String segment;

  String get path => '/staff/$segment';
}

/// Entries listed under More, in display order (Req 19.1).
enum StaffMoreItem {
  inventory('Inventory', 'inventory'),
  artisans('Artisans', 'artisans'),
  analytics('Analytics', 'analytics'),
  forecasting('Forecasting', 'forecasting'),
  notifications('Notifications', 'notifications'),
  settings('Settings', 'settings');

  const StaffMoreItem(this.label, this.segment);

  final String label;
  final String segment;

  String get path => '/staff/more/$segment';
}

/// Which navigation destinations each role may see (Req 6.10).
class RolePermissions {
  const RolePermissions._();

  static const Set<StaffDestination> _all = {
    StaffDestination.dashboard,
    StaffDestination.orders,
    StaffDestination.products,
    StaffDestination.production,
    StaffDestination.more,
  };

  static const Map<AppRole, Set<StaffDestination>> destinations = {
    AppRole.customer: {},
    AppRole.seller: _all,
    AppRole.admin: _all,
    AppRole.artisan: {StaffDestination.production},
  };

  static const Map<AppRole, Set<StaffMoreItem>> moreItems = {
    AppRole.customer: {},
    AppRole.seller: {...StaffMoreItem.values},
    AppRole.admin: {...StaffMoreItem.values},
    AppRole.artisan: {},
  };

  /// Permitted staff destinations in canonical order.
  static List<StaffDestination> staffDestinationsFor(AppRole role) => [
        for (final d in StaffDestination.values)
          if (destinations[role]!.contains(d)) d,
      ];

  /// Permitted More entries in canonical order.
  static List<StaffMoreItem> moreItemsFor(AppRole role) => [
        for (final m in StaffMoreItem.values)
          if (moreItems[role]!.contains(m)) m,
      ];

  /// First screen after sign-in for [role].
  static String homePath(AppRole role) {
    if (!role.isStaff) return '/';
    return staffDestinationsFor(role).first.path;
  }

  /// Whether [role] may open the staff [location] (`/staff/...`).
  static bool canOpenStaffPath(AppRole role, String location) {
    if (!role.isStaff) return false;
    final segments = Uri.parse(location).pathSegments;
    if (segments.isEmpty || segments.first != 'staff') return false;
    if (segments.length == 1) return true; // `/staff` redirects to home.
    final dest = StaffDestination.values
        .where((d) => d.segment == segments[1])
        .firstOrNull;
    if (dest == null || !destinations[role]!.contains(dest)) return false;
    if (dest == StaffDestination.more && segments.length > 2) {
      final item = StaffMoreItem.values
          .where((m) => m.segment == segments[2])
          .firstOrNull;
      return item != null && moreItems[role]!.contains(item);
    }
    return true;
  }
}
