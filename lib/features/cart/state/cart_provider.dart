import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/badge.dart';
import '../../../core/network/api_client.dart';
import '../../../core/network/app_failure.dart';
import '../../../core/storage/legacy_local_store.dart';
import '../../auth/data/auth_user.dart';
import '../../auth/state/session_provider.dart';
import '../../catalogue/data/catalogue_models.dart';
import '../../catalogue/data/catalogue_repository.dart';
import '../data/cart_models.dart';
import '../data/cart_repository.dart';
import '../data/guest_cart_repository.dart';

final cartRepositoryProvider = Provider<CartRepository>(
    (ref) => CartRepository(ref.watch(apiClientProvider)));

/// What the cart screen shows: the cart, plus the guest items that were not
/// merged at sign-in (Req 11.13).
class CartState {
  const CartState({
    this.cart = const CartData(),
    this.signedIn = false,
    this.notMerged = const [],
    this.mergePending = false,
  });

  final CartData cart;
  final bool signedIn;
  final List<NotMergedItem> notMerged;

  /// The merge failed; the guest cart is kept on the device (Req 11.13).
  final bool mergePending;

  CartState copyWith({
    CartData? cart,
    List<NotMergedItem>? notMerged,
    bool? mergePending,
  }) =>
      CartState(
        cart: cart ?? this.cart,
        signedIn: signedIn,
        notMerged: notMerged ?? this.notMerged,
        mergePending: mergePending ?? this.mergePending,
      );
}

/// Customer id when a Customer is signed in, otherwise null (guest cart).
final _cartCustomerIdProvider = Provider<int?>((ref) {
  final s = ref.watch(sessionProvider);
  return s is SessionSignedIn && s.role == AppRole.customer ? s.user.id : null;
});

const _lineLimitMessage = 'A single line can hold at most 20 units';

/// Message for a failed cart change: the allowed range (422), the 20 per line
/// limit, or the available quantity (409, Req 11.2, 11.3, 11.6).
String cartFailureMessage(AppFailure e) {
  if (e is ConflictFailure && e.code == 'insufficient_stock') {
    for (final d in e.details) {
      if (d is Map && d['available'] is num) {
        final n = (d['available'] as num).toInt();
        return n <= 0 ? 'Out of stock' : 'Only $n available';
      }
    }
  }
  if (e is NetworkFailure || e is TimeoutFailure) {
    return 'Network unavailable. Try again.';
  }
  return e.message;
}

class CartNotifier extends AsyncNotifier<CartState> {
  /// Catalogue products used to price guest lines.
  final Map<String, CatalogueProduct?> _products = {};

  GuestCartRepository? _local;

  @override
  Future<CartState> build() async {
    final userId = ref.watch(_cartCustomerIdProvider);
    final store = await ref.watch(legacyLocalStoreProvider.future);
    final local = _local = GuestCartRepository(store);
    if (userId == null) {
      return CartState(cart: await _guestView(local.load()));
    }

    final remote = ref.read(cartRepositoryProvider);
    final guest = local.load();
    var notMerged = <NotMergedItem>[];
    var mergePending = false;
    CartData? cart;
    if (guest.isNotEmpty) {
      try {
        final result = await remote.merge(guest);
        cart = result.cart;
        final names = {for (final l in cart.lines) l.key: l.name};
        notMerged = [
          for (final n in result.notMerged) n.withName(names[n.key]),
        ];
        if (notMerged.isEmpty) {
          await local.clear();
        } else {
          // Keep what was left out on the device (Req 11.13).
          await local.save({
            for (final n in notMerged)
              if (n.quantity > 0) n.key: n.quantity,
          });
        }
      } on AppFailure {
        mergePending = true; // login stays successful, guest cart is kept
      }
    }
    cart ??= await remote.fetch();
    return CartState(
        cart: cart,
        signedIn: true,
        notMerged: notMerged,
        mergePending: mergePending);
  }

  /// Reloads, which also retries a failed merge.
  void retry() => ref.invalidateSelf();

  void dismissNotMerged() {
    final s = state.value;
    if (s != null) state = AsyncData(s.copyWith(notMerged: const []));
  }

  // ---- guest cart ---------------------------------------------------------

  Future<CartData> _guestView(Map<String, int> quantities) async {
    final lines = <CartLine>[];
    for (final e in quantities.entries) {
      final k = parseCartKey(e.key);
      final product = await _product(k.productId);
      lines.add(_guestLine(k.productId, k.variationId, e.value, product));
    }
    return CartData.fromLines(lines);
  }

  Future<CatalogueProduct?> _product(String id) async {
    if (_products.containsKey(id)) return _products[id];
    try {
      final p =
          await CatalogueRepository(ref.read(apiClientProvider)).getProduct(id);
      return _products[id] = p;
    } on NotFoundFailure {
      return _products[id] = null; // product no longer exists
    }
  }

  CartLine _guestLine(
      String productId, int? variationId, int qty, CatalogueProduct? p) {
    if (p == null) {
      return CartLine(
          productId: productId,
          variationId: variationId,
          quantity: qty,
          unitPriceSen: 0,
          lineTotalSen: 0,
          available: false);
    }
    final v = variationId == null
        ? null
        : p.variations.where((x) => x.id == variationId).firstOrNull;
    final missingVariation = variationId != null && v == null;
    final stock = v?.stockQuantity ?? p.stockQuantity;
    final unit = v?.priceSen ?? p.priceSen;
    return CartLine(
      productId: productId,
      variationId: variationId,
      name: p.name,
      variationLabel: v?.label,
      imageUrl: p.firstImage,
      quantity: qty,
      unitPriceSen: unit,
      lineTotalSen: unit * qty,
      available: !missingVariation && (v?.isActive ?? true) && stock > 0,
      availableQuantity: stock,
    );
  }

  // ---- changes ------------------------------------------------------------

  Future<CartState?> _current() async {
    try {
      return state.value ?? await future;
    } catch (_) {
      return null;
    }
  }

  void _set(CartState s, CartData cart) =>
      state = AsyncData(s.copyWith(cart: cart));

  /// Adds [quantity] of [product]. Returns an error message, or null when the
  /// cart was updated. The cart is left unchanged on error.
  Future<String?> addProduct(CatalogueProduct product, int? variationId,
      {int quantity = 1}) async {
    if (quantity < 1 || quantity > maxLineQuantity) {
      return 'Quantity must be an integer from 1 to $maxLineQuantity';
    }
    final s = await _current();
    if (s == null) return 'Cart is not available. Try again.';
    try {
      if (s.signedIn) {
        _set(
            s,
            await ref
                .read(cartRepositoryProvider)
                .add(product.id, variationId, quantity));
        return null;
      }
      final local = _local!;
      final quantities = local.load();
      final key = cartKey(product.id, variationId);
      final total = (quantities[key] ?? 0) + quantity;
      if (total > maxLineQuantity) return _lineLimitMessage;
      final variation = variationId == null
          ? null
          : product.variations.where((v) => v.id == variationId).firstOrNull;
      final stock = variation?.stockQuantity ?? product.stockQuantity;
      if (total > stock) {
        return stock <= 0 ? 'Out of stock' : 'Only $stock available';
      }
      _products[product.id] = product;
      quantities[key] = total;
      await local.save(quantities);
      _set(s, await _guestView(quantities));
      return null;
    } on AppFailure catch (e) {
      return cartFailureMessage(e);
    }
  }

  /// Sets the quantity of [line]; 0 removes it (Req 11.8).
  Future<String?> setQuantity(CartLine line, int quantity) async {
    if (quantity < 0) {
      return 'Quantity must be an integer from 1 to $maxLineQuantity';
    }
    if (quantity > maxLineQuantity) return _lineLimitMessage;
    final s = await _current();
    if (s == null) return 'Cart is not available. Try again.';
    try {
      if (s.signedIn) {
        final repo = ref.read(cartRepositoryProvider);
        _set(
            s,
            quantity == 0 && line.id != null
                ? await repo.remove(line.id!)
                : await repo.setQuantity(
                    line.productId, line.variationId, quantity));
        return null;
      }
      if (quantity > line.availableQuantity && quantity > line.quantity) {
        return line.availableQuantity <= 0
            ? 'Out of stock'
            : 'Only ${line.availableQuantity} available';
      }
      final local = _local!;
      final quantities = local.load();
      if (quantity == 0) {
        quantities.remove(line.key);
      } else {
        quantities[line.key] = quantity;
      }
      await local.save(quantities);
      _set(s, await _guestView(quantities));
      return null;
    } on AppFailure catch (e) {
      return cartFailureMessage(e);
    }
  }

  Future<String?> remove(CartLine line) => setQuantity(line, 0);
}

final cartProvider =
    AsyncNotifierProvider<CartNotifier, CartState>(CartNotifier.new,
        // Show the error and Retry at once instead of retrying silently.
        retry: (retryCount, error) => null);

/// Units in the cart, for the Cart tab badge.
final cartCountProvider =
    Provider<int>((ref) => ref.watch(cartProvider).value?.cart.itemCount ?? 0);

/// Badge text: null when 0, `99+` above 99 (Req 18.4 to 18.6).
final cartBadgeProvider =
    Provider<String?>((ref) => badgeLabel(ref.watch(cartCountProvider)));
