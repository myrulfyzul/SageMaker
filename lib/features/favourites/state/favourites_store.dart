import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/storage/legacy_local_store.dart';
import '../data/local_favourites_repository.dart';

/// Resolved only after [legacyLocalStoreProvider] has loaded.
final localFavouritesRepositoryProvider = Provider<LocalFavouritesRepository>(
    (ref) => LocalFavouritesRepository(ref.watch(legacyLocalStoreProvider).requireValue));

/// Local favourites with change notification (the old `FavoritesStore`).
class FavoritesStore extends ChangeNotifier {
  FavoritesStore(this._repository) : _favoriteIds = _repository.load();

  final LocalFavouritesRepository _repository;
  final Set<String> _favoriteIds;

  bool contains(String productId) => _favoriteIds.contains(productId);
  int get count => _favoriteIds.length;

  Future<void> toggle(String productId) async {
    if (!_favoriteIds.add(productId)) {
      _favoriteIds.remove(productId);
    }
    notifyListeners();
    await _repository.save(_favoriteIds);
  }
}

final favoritesStoreProvider = Provider<FavoritesStore>((ref) {
  final store = FavoritesStore(ref.watch(localFavouritesRepositoryProvider));
  ref.onDispose(store.dispose);
  return store;
});
