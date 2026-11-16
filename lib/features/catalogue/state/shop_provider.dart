import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_client.dart';
import '../../cart/state/cart_provider.dart';
import '../data/catalogue_models.dart';
import '../data/catalogue_repository.dart';

final catalogueRepositoryProvider = Provider<CatalogueRepository>(
    (ref) => CatalogueRepository(ref.watch(apiClientProvider)));

final categoriesProvider = FutureProvider<List<CategoryRef>>(
    (ref) => ref.watch(catalogueRepositoryProvider).categories());

final productDetailProvider = FutureProvider.family<CatalogueProduct, String>(
    (ref, id) => ref.watch(catalogueRepositoryProvider).getProduct(id));

/// Home sections load independently so one failure leaves the others (Req 8.8).
final bestSellersProvider = FutureProvider<List<CatalogueProduct>>(
    (ref) => ref.watch(catalogueRepositoryProvider).bestSellers());
final newArrivalsProvider = FutureProvider<List<CatalogueProduct>>(
    (ref) => ref.watch(catalogueRepositoryProvider).newArrivals());
final recommendationsProvider = FutureProvider<List<CatalogueProduct>>(
    (ref) => ref.watch(catalogueRepositoryProvider).recommendations());

/// Shop list state: accumulated pages for the current [ShopQuery].
class ShopState {
  const ShopState({
    this.query = const ShopQuery(),
    this.items = const [],
    this.total = 0,
    this.loading = false,
    this.loadingMore = false,
    this.error,
    this.moreError,
  });
  final ShopQuery query;
  final List<CatalogueProduct> items;
  final int total;
  final bool loading;
  final bool loadingMore;
  final Object? error;
  final Object? moreError;

  bool get hasMore => items.length < total;
}

class ShopNotifier extends Notifier<ShopState> {
  int _generation = 0;

  @override
  ShopState build() => const ShopState(loading: true);

  /// Replaces the list with the first page of [query].
  Future<void> load(ShopQuery query) async {
    final gen = ++_generation;
    state = ShopState(query: query, loading: true, items: state.items);
    try {
      final page =
          await ref.read(catalogueRepositoryProvider).listProducts(query);
      if (gen != _generation) return;
      state = ShopState(query: query, items: page.items, total: page.total);
    } catch (e) {
      if (gen != _generation) return;
      state = ShopState(query: query, error: e);
    }
  }

  Future<void> retry() => load(state.query);

  Future<void> loadMore() async {
    if (state.loading || state.loadingMore || !state.hasMore) return;
    final gen = _generation;
    final s = state;
    state = ShopState(
        query: s.query, items: s.items, total: s.total, loadingMore: true);
    try {
      final page = await ref
          .read(catalogueRepositoryProvider)
          .listProducts(s.query, offset: s.items.length);
      if (gen != _generation) return;
      state = ShopState(
          query: s.query,
          items: [...s.items, ...page.items],
          total: page.total);
    } catch (e) {
      if (gen != _generation) return;
      state = ShopState(
          query: s.query, items: s.items, total: s.total, moreError: e);
    }
  }
}

final shopProvider =
    NotifierProvider<ShopNotifier, ShopState>(ShopNotifier.new);

/// Add-to-cart hook: returns an error message, or null on success. Uses the
/// server cart when signed in and the guest cart otherwise (Req 11.1).
typedef AddToCart = Future<String?> Function(
    CatalogueProduct product, int? variationId);

final addToCartProvider = Provider<AddToCart>((ref) => (product, variationId) =>
    ref.read(cartProvider.notifier).addProduct(product, variationId));
