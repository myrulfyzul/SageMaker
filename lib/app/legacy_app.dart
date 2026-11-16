import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/legacy_palette.dart';
import '../core/storage/legacy_local_store.dart';
import '../features/about/ui/more_page.dart';
import '../features/cart/state/cart_store.dart';
import '../features/cart/ui/cart_page.dart';
import '../features/catalogue/data/product.dart';
import '../features/catalogue/state/catalogue_provider.dart';
import '../features/catalogue/ui/product_detail_page.dart';
import '../features/catalogue/ui/shop_page.dart';
import '../features/checkout/data/legacy_checkout_repository.dart';
import '../features/favourites/state/favourites_store.dart';
import '../features/favourites/ui/favourites_page.dart';
import '../features/home/ui/home_page.dart';
import '../features/orders/state/orders_store.dart';
import '../features/orders/ui/orders_page.dart';

/// Opens the prototype stores (same shared_preferences keys as before) and
/// shows the prototype screens. Kept while the router and role shells replace
/// it; behaviour is unchanged from the old main.dart.
class LegacyApp extends ConsumerWidget {
  const LegacyApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final store = ref.watch(legacyLocalStoreProvider);
    return store.when(
      data: (_) => SagemakerApp(
        favorites: ref.watch(favoritesStoreProvider),
        cart: ref.watch(cartStoreProvider),
        orders: ref.watch(ordersStoreProvider),
        checkout: ref.watch(legacyCheckoutRepositoryProvider),
        products: ref.watch(productsProvider.future),
      ),
      loading: () => const MaterialApp(
          home: Scaffold(body: Center(child: CircularProgressIndicator()))),
      error: (e, st) => const MaterialApp(
          home: Scaffold(body: Center(child: Text('Cannot start the app')))),
    );
  }
}


class SagemakerApp extends StatelessWidget {
  const SagemakerApp({super.key, required this.favorites, required this.cart, required this.orders, required this.checkout, required this.products});
  final FavoritesStore favorites;
  final CartStore cart;
  final OrdersStore orders;
  final LegacyCheckoutRepository checkout;
  final Future<List<Product>> products;

  @override
  Widget build(BuildContext context) => MaterialApp(
        title: 'Sagemaker Asia',
        debugShowCheckedModeBanner: false,
        theme: ThemeData(
          useMaterial3: true,
          scaffoldBackgroundColor: cream,
          colorScheme: ColorScheme.fromSeed(seedColor: forest, primary: forest),
          appBarTheme: const AppBarTheme(
            backgroundColor: cream,
            surfaceTintColor: Colors.transparent,
          ),
          cardTheme: CardThemeData(
            color: Colors.white,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(18),
            ),
            elevation: 0,
          ),
          filledButtonTheme: FilledButtonThemeData(
            style: FilledButton.styleFrom(
              backgroundColor: forest,
              foregroundColor: Colors.white,
              minimumSize: const Size(0, 46),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(12),
              ),
            ),
          ),
        ),
        home: AppShell(favorites: favorites, cart: cart, orders: orders, checkout: checkout, products: products),
      );
}

class AppShell extends StatefulWidget {
  const AppShell({super.key, required this.favorites, required this.cart, required this.orders, required this.checkout, required this.products});
  final FavoritesStore favorites;
  final CartStore cart;
  final OrdersStore orders;
  final LegacyCheckoutRepository checkout;
  final Future<List<Product>> products;

  @override
  State<AppShell> createState() => _AppShellState();
}

class _AppShellState extends State<AppShell> {
  int currentTab = 0;
  Future<List<Product>> get products => widget.products;

  void goTo(int tab) => setState(() => currentTab = tab);

  void showProduct(Product product) {
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (context) => ProductDetailPage(
          product: product,
          favorites: widget.favorites,
          cart: widget.cart,
          onCart: showCart,
        ),
      ),
    );
  }

  void showCart() {
    Navigator.of(context).push(MaterialPageRoute<void>(
      builder: (context) => CartPage(products: products, cart: widget.cart, orders: widget.orders, checkout: widget.checkout),
    ));
  }

  @override
  Widget build(BuildContext context) {
    final tabs = <Widget>[
      HomePage(products: products, onShop: () => goTo(1), onAbout: () => goTo(4), favorites: widget.favorites, onProductTap: showProduct),
      ShopPage(products: products, favorites: widget.favorites, onProductTap: showProduct, onCart: showCart),
      FavoritesPage(products: products, favorites: widget.favorites, onProductTap: showProduct, onShop: () => goTo(1)),
      OrdersPage(orders: widget.orders),
      const MorePage(),
    ];
    return Scaffold(
      appBar: AppBar(
        titleSpacing: 20,
        title: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              decoration: BoxDecoration(
                color: forest,
                borderRadius: BorderRadius.circular(9),
              ),
              padding: const EdgeInsets.all(7),
              child: const Icon(Icons.spa_outlined, color: Colors.white, size: 20),
            ),
            const SizedBox(width: 10),
            const Text('sagemaker', style: TextStyle(fontWeight: FontWeight.w800, fontSize: 23, letterSpacing: -0.8, color: deep)),
          ],
        ),
        actions: [
          IconButton(
            tooltip: 'Your in-app cart',
            icon: AnimatedBuilder(animation: widget.cart, builder: (context, _) => Badge(
              isLabelVisible: widget.cart.count > 0,
              label: Text('${widget.cart.count}'),
              child: const Icon(Icons.shopping_bag_outlined),
            )),
            onPressed: showCart,
          ),
          const SizedBox(width: 8),
        ],
      ),
      body: IndexedStack(index: currentTab, children: tabs),
      bottomNavigationBar: NavigationBar(
        selectedIndex: currentTab,
        onDestinationSelected: goTo,
        height: 72,
        backgroundColor: Colors.white,
        indicatorColor: const Color(0xFFE3EEE7),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.home_outlined), selectedIcon: Icon(Icons.home), label: 'Home'),
          NavigationDestination(icon: Icon(Icons.storefront_outlined), selectedIcon: Icon(Icons.storefront), label: 'Shop'),
          NavigationDestination(icon: Icon(Icons.favorite_border), selectedIcon: Icon(Icons.favorite), label: 'Saved'),
          NavigationDestination(icon: Icon(Icons.local_shipping_outlined), selectedIcon: Icon(Icons.local_shipping), label: 'Orders'),
          NavigationDestination(icon: Icon(Icons.more_horiz), label: 'More'),
        ],
      ),
    );
  }
}
