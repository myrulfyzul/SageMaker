import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_client.dart';
import '../../../core/network/app_failure.dart';
import '../../../core/storage/legacy_local_store.dart';
import '../../auth/data/auth_user.dart';
import '../../auth/state/session_provider.dart';
import '../../catalogue/data/product.dart';
import '../../catalogue/state/catalogue_provider.dart';
import '../data/favourites_repository.dart';
import '../data/local_favourites_repository.dart';
import 'favourites_store.dart';

final favouritesRepositoryProvider = Provider<FavouritesRepository>(
    (ref) => FavouritesRepository(ref.watch(apiClientProvider)));

/// The favourites on screen: the server list when signed in, the device list
/// for guests.
class FavouritesState {
  const FavouritesState({
    this.products = const [],
    this.signedIn = false,
    this.mergePending = false,
  });
  final List<Product> products;
  final bool signedIn;

  /// Local favourites are still on the device because the upload failed; it is
  /// retried at the next sign-in or on retry (Req 10.11).
  final bool mergePending;

  Set<String> get ids => {for (final p in products) p.id};
  bool contains(String productId) => products.any((p) => p.id == productId);
}

/// Customer id when a Customer is signed in, otherwise null.
final _customerIdProvider = Provider<int?>((ref) {
  final s = ref.watch(sessionProvider);
  return s is SessionSignedIn && s.role == AppRole.customer ? s.user.id : null;
});

class FavouritesNotifier extends AsyncNotifier<FavouritesState> {
  @override
  Future<FavouritesState> build() async {
    final userId = ref.watch(_customerIdProvider);
    await ref.watch(legacyLocalStoreProvider.future);
    final local = ref.watch(localFavouritesRepositoryProvider);
    if (userId == null) return _guest(local);

    final remote = ref.read(favouritesRepositoryProvider);
    final localIds = local.load();
    var mergePending = false;
    if (localIds.isNotEmpty) {
      try {
        final merged = await remote.merge(localIds);
        // Clear only after the server confirmed the upload (Req 10.10).
        await local.clear();
        return FavouritesState(products: merged, signedIn: true);
      } on AppFailure {
        mergePending = true; // keep the local copy (Req 10.11)
      }
    }
    final products = await remote.list();
    return FavouritesState(
        products: products, signedIn: true, mergePending: mergePending);
  }

  Future<FavouritesState> _guest(LocalFavouritesRepository local) async {
    final ids = local.load();
    if (ids.isEmpty) return const FavouritesState();
    final all = await ref.read(productsProvider.future);
    return FavouritesState(products: [
      for (final p in all)
        if (ids.contains(p.id)) p,
    ]);
  }

  /// Reloads, which also retries a failed merge.
  void retry() => ref.invalidateSelf();

  /// Adds or removes [product]. Throws [AppFailure] when the server refuses;
  /// the list is left unchanged in that case.
  Future<void> toggle(Product product) async {
    final current = state.value;
    if (current == null) return;
    final saved = current.contains(product.id);
    if (current.signedIn) {
      final remote = ref.read(favouritesRepositoryProvider);
      if (saved) {
        await remote.remove(product.id);
      } else {
        await remote.add(product.id);
      }
    }
    final products = saved
        ? [
            for (final p in current.products)
              if (p.id != product.id) p
          ]
        : [product, ...current.products];
    if (!current.signedIn) {
      await ref
          .read(localFavouritesRepositoryProvider)
          .save({for (final p in products) p.id});
    }
    state = AsyncData(FavouritesState(
        products: products,
        signedIn: current.signedIn,
        mergePending: current.mergePending));
  }
}

final favouritesProvider = AsyncNotifierProvider<FavouritesNotifier,
        FavouritesState>(FavouritesNotifier.new,
    // Show the error and Retry at once instead of retrying silently (Req 10.8).
    retry: (retryCount, error) => null);
