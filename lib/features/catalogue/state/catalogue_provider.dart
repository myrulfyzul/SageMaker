import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_client.dart';
import '../data/product.dart';
import '../data/product_repository.dart';

final productRepositoryProvider = Provider<ProductRepository>((ref) =>
    ProductRepository(
        client: ref.watch(apiClientProvider), loadAsset: rootBundle.loadString));

/// Products, server first, bundled JSON when the server is unavailable.
final productsProvider = FutureProvider<List<Product>>(
    (ref) => ref.watch(productRepositoryProvider).loadProducts());
