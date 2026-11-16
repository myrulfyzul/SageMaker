import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/widgets/badge_count.dart';
import '../../features/cart/state/cart_provider.dart';
import '../theme.dart';

/// Number of items in the cart, shown as the Cart badge (Req 18.4 to 18.6).
/// Follows the real cart (server cart when signed in, guest cart otherwise).
final cartItemCountProvider =
    Provider<int>((ref) => ref.watch(cartCountProvider));

/// Bottom bar with exactly Home, Shop, Favourites, Cart, Profile (Req 18.1).
/// Branch order in the router must match [customerDestinations].
class CustomerShell extends ConsumerWidget {
  const CustomerShell({super.key, required this.navigationShell});

  final StatefulNavigationShell navigationShell;

  static const customerDestinations =
      <({String label, IconData icon, IconData selectedIcon})>[
    (label: 'Home', icon: Icons.home_outlined, selectedIcon: Icons.home),
    (
      label: 'Shop',
      icon: Icons.storefront_outlined,
      selectedIcon: Icons.storefront
    ),
    (
      label: 'Favourites',
      icon: Icons.favorite_border,
      selectedIcon: Icons.favorite
    ),
    (
      label: 'Cart',
      icon: Icons.shopping_bag_outlined,
      selectedIcon: Icons.shopping_bag
    ),
    (label: 'Profile', icon: Icons.person_outline, selectedIcon: Icons.person),
  ];

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cartCount = ref.watch(cartItemCountProvider);
    return Scaffold(
      body: navigationShell,
      bottomNavigationBar: _FloatingBar(
          child: NavigationBar(
        selectedIndex: navigationShell.currentIndex,
        onDestinationSelected: (i) => navigationShell.goBranch(
          i,
          initialLocation: i == navigationShell.currentIndex,
        ),
        destinations: [
          for (var i = 0; i < customerDestinations.length; i++)
            NavigationDestination(
              label: customerDestinations[i].label,
              icon: i == 3
                  ? BadgeCount(
                      count: cartCount,
                      child: Icon(customerDestinations[i].icon))
                  : Icon(customerDestinations[i].icon),
              selectedIcon: i == 3
                  ? BadgeCount(
                      count: cartCount,
                      child: Icon(customerDestinations[i].selectedIcon))
                  : Icon(customerDestinations[i].selectedIcon),
            ),
        ],
      )),
    );
  }
}

/// Rounded, shadowed container that lifts the navigation bar off the edge.
class _FloatingBar extends StatelessWidget {
  const _FloatingBar({required this.child});
  final Widget child;

  @override
  Widget build(BuildContext context) => SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(12, 0, 12, 10),
          child: DecoratedBox(
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(26),
              boxShadow: softShadow(0.14),
            ),
            child: ClipRRect(
              borderRadius: BorderRadius.circular(26),
              child: MediaQuery.removePadding(
                  context: context, removeBottom: true, child: child),
            ),
          ),
        ),
      );
}
