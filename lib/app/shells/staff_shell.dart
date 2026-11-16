import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../features/auth/data/auth_user.dart';
import '../../features/auth/state/session_provider.dart';
import '../../core/widgets/ui_kit.dart';
import '../role_permissions.dart';
import '../theme.dart';

IconData _iconFor(StaffDestination d) => switch (d) {
      StaffDestination.dashboard => Icons.dashboard_outlined,
      StaffDestination.orders => Icons.receipt_long_outlined,
      StaffDestination.products => Icons.inventory_2_outlined,
      StaffDestination.production => Icons.handyman_outlined,
      StaffDestination.more => Icons.more_horiz,
    };

/// Bottom bar for Seller, Admin and Artisan users. Branch order in the router
/// is [StaffDestination.values]; only the destinations the role may see are
/// shown (Req 6.10, 19.1). A role with a single destination gets no bar.
class StaffShell extends ConsumerWidget {
  const StaffShell({super.key, required this.navigationShell});

  final StatefulNavigationShell navigationShell;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final session = ref.watch(sessionProvider);
    final role = session is SessionSignedIn ? session.role : AppRole.seller;
    final allowed = RolePermissions.staffDestinationsFor(role);
    final current = StaffDestination.values[navigationShell.currentIndex];
    var selected = allowed.indexOf(current);
    if (selected < 0) selected = 0;

    return Scaffold(
      appBar: AppBar(
        title: Text(current.label),
        actions: [
          IconButton(
            tooltip: 'Sign out',
            icon: const Icon(Icons.logout),
            onPressed: () => ref.read(sessionProvider.notifier).logout(),
          ),
        ],
      ),
      body: navigationShell,
      bottomNavigationBar: allowed.length < 2
          ? null
          : NavigationBar(
              selectedIndex: selected,
              onDestinationSelected: (i) {
                final dest = allowed[i];
                navigationShell.goBranch(
                  dest.index,
                  initialLocation: dest == current,
                );
              },
              destinations: [
                for (final d in allowed)
                  NavigationDestination(
                      icon: Icon(_iconFor(d)), label: d.label),
              ],
            ),
    );
  }
}

/// The More tab: lists the permitted entries in order (Req 19.1).
class StaffMoreScreen extends ConsumerWidget {
  const StaffMoreScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final session = ref.watch(sessionProvider);
    final role = session is SessionSignedIn ? session.role : AppRole.customer;
    final items = RolePermissions.moreItemsFor(role);
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        for (final (i, item) in items.indexed)
          FadeSlideIn(
            index: i,
            child: Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: SoftCard(
                padding: EdgeInsets.zero,
                child: Material(
                  type: MaterialType.transparency,
                  child: ListTile(
                    contentPadding:
                        const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
                    leading: Container(
                      width: 42,
                      height: 42,
                      decoration: BoxDecoration(
                        gradient: kHeroGradient,
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child:
                          Icon(_moreIcon(item), color: Colors.white, size: 22),
                    ),
                    title: Text(item.label,
                        style: const TextStyle(fontWeight: FontWeight.w700)),
                    subtitle: Text(_moreHint(item)),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: () => context.push(item.path),
                  ),
                ),
              ),
            ),
          ),
      ],
    );
  }
}

IconData _moreIcon(StaffMoreItem i) => switch (i) {
      StaffMoreItem.inventory => Icons.warehouse_outlined,
      StaffMoreItem.artisans => Icons.groups_outlined,
      StaffMoreItem.analytics => Icons.insights_outlined,
      StaffMoreItem.forecasting => Icons.auto_graph,
      StaffMoreItem.notifications => Icons.notifications_none,
      StaffMoreItem.settings => Icons.tune,
    };

String _moreHint(StaffMoreItem i) => switch (i) {
      StaffMoreItem.inventory => 'Stock levels and low-stock alerts',
      StaffMoreItem.artisans => 'Profiles, skills and assignments',
      StaffMoreItem.analytics => 'Sales, orders and best sellers',
      StaffMoreItem.forecasting => 'AI demand forecast for planning',
      StaffMoreItem.notifications => 'Updates for your team',
      StaffMoreItem.settings => 'Store settings',
    };
