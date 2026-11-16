import '../../../core/storage/legacy_local_store.dart';

/// Favourites saved on this device by the earlier prototype (key
/// `sagemaker_saved_product_ids`). Used while signed out and as the source for
/// the first-sign-in upload (Req 10.10, 10.11).
class LocalFavouritesRepository {
  LocalFavouritesRepository(this._store);

  final LegacyLocalStore _store;

  Set<String> load() => _store.readFavouriteIds().toSet();

  Future<void> save(Iterable<String> ids) => _store.writeFavouriteIds(ids);

  /// Clear only after the server confirmed the upload (Req 10.10).
  Future<void> clear() => _store.clearFavourites();
}
