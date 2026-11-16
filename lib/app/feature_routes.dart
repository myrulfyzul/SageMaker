import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../features/about/ui/about_screen.dart';
import '../features/admin/analytics/ui/analytics_screen.dart';
import '../features/admin/dashboard/ui/dashboard_screen.dart';
import '../features/notifications/ui/notifications_screen.dart';
import '../features/profile/ui/profile_screen.dart';
import '../features/settings/ui/connection_settings_screen.dart';
import '../features/auth/state/session_provider.dart';
import '../features/auth/ui/login_screen.dart';
import '../features/auth/ui/register_screen.dart';
import '../features/cart/ui/cart_screen.dart';
import '../features/catalogue/ui/product_detail_screen.dart';
import '../features/catalogue/ui/shop_screen.dart';
import '../features/checkout/ui/checkout_screen.dart';
import '../features/custom_orders/ui/custom_order_detail_screen.dart';
import '../features/custom_orders/ui/custom_order_form_screen.dart';
import '../features/custom_orders/ui/custom_orders_screen.dart';
import '../features/favourites/ui/favourites_screen.dart';
import '../features/payment/ui/confirmation_screen.dart';
import '../features/payment/ui/payment_screen.dart';
import '../features/payment/ui/payment_wait_screen.dart';
import '../features/home/ui/home_screen.dart';
import '../features/welcome/ui/welcome_screen.dart';
import '../features/orders/ui/my_orders_screen.dart';
import '../features/orders/ui/order_tracking_screen.dart';
import '../features/admin/orders/ui/staff_order_detail_screen.dart';
import '../features/admin/orders/ui/staff_orders_screen.dart';
import '../features/admin/inventory/ui/inventory_screen.dart';
import '../features/admin/artisans/ui/artisans_screen.dart';
import '../features/admin/production/ui/production_screen.dart';
import '../features/admin/products/ui/admin_products_screen.dart';
import '../features/admin/custom_orders/ui/staff_custom_orders_screen.dart';
import '../features/admin/forecasting/ui/forecasting_screen.dart';
import '../features/admin/notifications/ui/staff_notifications_screen.dart';
import '../features/admin/settings/ui/staff_settings_screen.dart';
import 'navigation_memory.dart';
import 'placeholder_screen.dart';
import 'role_permissions.dart';
import 'shells/staff_shell.dart';

/// Composition point for every feature screen. Feature tasks replace the
/// placeholder builders below; `router.dart` is not edited for features.

GoRoute _page(String path, Widget Function(GoRouterState s) build) =>
    GoRoute(path: path, builder: (context, state) => build(state));

/// Customer tabs, in the order of the bottom bar (Req 18.1).
List<StatefulShellBranch> customerBranches() => [
      StatefulShellBranch(routes: [_page('/', (_) => const HomeScreen())]),
      StatefulShellBranch(routes: [
        _page(
            '/shop',
            (s) => ShopScreen(
                initialQuery: s.uri.queryParameters['q'],
                initialCategory: s.uri.queryParameters['category']))
      ]),
      StatefulShellBranch(
          routes: [_page('/favourites', (_) => const FavouritesScreen())]),
      StatefulShellBranch(routes: [_page('/cart', (_) => const CartScreen())]),
      StatefulShellBranch(
          routes: [_page('/profile', (_) => const ProfileScreen())]),
    ];

/// Customer screens outside the tab bar (Req 18.3).
List<RouteBase> customerRoutes() => [
      _page('/product/:id',
          (s) => ProductDetailScreen(productId: s.pathParameters['id']!)),
      _page('/checkout', (_) => const CheckoutScreen()),
      // Declared before '/payment/:orderId' so 'wait' is not read as an order id.
      GoRoute(
        path: '/payment/wait/:paymentId',
        builder: (context, state) => PaymentWaitScreen(
          paymentId: state.pathParameters['paymentId']!,
          checkoutUrl: state.extra is String ? state.extra as String : null,
        ),
      ),
      _page('/payment/:orderId',
          (s) => PaymentScreen(orderId: s.pathParameters['orderId']!)),
      _page('/confirmation/:orderId',
          (s) => ConfirmationScreen(orderId: s.pathParameters['orderId']!)),
      _page('/orders', (_) => const MyOrdersScreen()),
      _page('/orders/:id',
          (s) => OrderTrackingScreen(orderId: s.pathParameters['id']!)),
      _page('/notifications', (_) => const NotificationsScreen()),
      _page('/custom-orders', (_) => const CustomOrdersScreen()),
      _page('/custom-orders/new', (_) => const CustomOrderFormScreen()),
      _page(
          '/custom-orders/:id',
          (s) => CustomOrderDetailScreen(
              orderId: int.tryParse(s.pathParameters['id']!) ?? 0)),
    ];

/// Screens open to everyone, signed in or not.
List<RouteBase> publicRoutes() => [
      _page('/welcome', (_) => const WelcomeScreen()),
      _page('/about', (_) => const AboutScreen()),
      _page('/settings/connection', (_) => const ConnectionSettingsScreen()),
      _page('/register', (_) => const RegisterScreen()),
      GoRoute(path: '/login', builder: (context, state) => const LoginScreen()),
    ];

/// Staff tabs, in the order of [StaffDestination.values] (Req 19.1).
List<StatefulShellBranch> staffBranches() => [
      StatefulShellBranch(routes: [
        _page(StaffDestination.dashboard.path, (_) => const DashboardScreen())
      ]),
      StatefulShellBranch(routes: [
        GoRoute(
          path: StaffDestination.orders.path,
          builder: (context, state) => const StaffOrdersScreen(),
          routes: [
            // Declared before ':id' so it is not read as an order id.
            GoRoute(
              path: 'custom-orders',
              builder: (context, state) => const StaffCustomOrdersScreen(),
            ),
            GoRoute(
              path: ':id',
              builder: (context, state) =>
                  StaffOrderDetailScreen(orderId: state.pathParameters['id']!),
            ),
          ],
        ),
      ]),
      StatefulShellBranch(routes: [
        _page(
            StaffDestination.products.path, (_) => const AdminProductsScreen())
      ]),
      StatefulShellBranch(routes: [
        _page(StaffDestination.production.path, (_) => const ProductionScreen())
      ]),
      StatefulShellBranch(routes: [
        GoRoute(
          path: StaffDestination.more.path,
          builder: (context, state) => const StaffMoreScreen(),
          routes: [
            for (final item in StaffMoreItem.values)
              GoRoute(
                path: item.segment,
                builder: (context, state) => switch (item) {
                  StaffMoreItem.analytics => const AnalyticsScreen(),
                  StaffMoreItem.inventory => const InventoryScreen(),
                  StaffMoreItem.artisans => const ArtisansScreen(),
                  StaffMoreItem.forecasting => const ForecastingScreen(),
                  StaffMoreItem.notifications =>
                    const StaffNotificationsScreen(),
                  StaffMoreItem.settings => const StaffSettingsScreen(),
                },
              ),
          ],
        ),
      ]),
    ];

/// Temporary login screen. The auth feature replaces it. Cancel returns to
/// the previous screen (Req 18.8) and the server-unreachable error is shown
/// (Req 5.11).
class LoginPlaceholder extends ConsumerWidget {
  const LoginPlaceholder({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final session = ref.watch(sessionProvider);
    return Scaffold(
      appBar: AppBar(
        title: const Text('Sign in'),
        leading: IconButton(
          tooltip: 'Cancel',
          icon: const Icon(Icons.close),
          onPressed: () => cancelLogin(
              GoRouter.of(context), ref.read(navigationMemoryProvider)),
        ),
      ),
      body: PlaceholderScreen(
        'Sign in',
        actions: [
          if (session is SessionServerUnreachable)
            Text(session.message,
                style: TextStyle(color: Theme.of(context).colorScheme.error)),
        ],
      ),
    );
  }
}
