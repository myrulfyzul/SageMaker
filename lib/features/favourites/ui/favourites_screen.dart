import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/widgets/async_value_view.dart';
import '../../catalogue/data/product.dart';
import '../state/favourites_provider.dart';

/// Heart button backed by [favouritesProvider].
class FavouriteToggle extends ConsumerWidget {
  const FavouriteToggle({super.key, required this.product});
  final Product product;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final saved = ref.watch(favouritesProvider
        .select((v) => v.value?.contains(product.id) ?? false));
    return IconButton(
      tooltip: saved ? 'Remove from favourites' : 'Save to favourites',
      icon: Icon(saved ? Icons.favorite : Icons.favorite_border),
      onPressed: () async {
        final messenger = ScaffoldMessenger.of(context);
        try {
          await ref.read(favouritesProvider.notifier).toggle(product);
        } catch (_) {
          messenger.showSnackBar(
              const SnackBar(content: Text('Could not update favourites. Try again.')));
        }
      },
    );
  }
}

/// Favourites tab: loading, error with retry, empty state and the list.
class FavouritesScreen extends ConsumerWidget {
  const FavouritesScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final value = ref.watch(favouritesProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Favourites')),
      body: AsyncValueView<FavouritesState>(
        value: value,
        onRetry: () => ref.read(favouritesProvider.notifier).retry(),
        isEmpty: (s) => s.products.isEmpty && !s.mergePending,
        emptyMessage: 'No favourites yet. Tap the heart on a product to save it.',
        emptyActionLabel: 'Explore products',
        onEmptyAction: () => context.go('/shop'),
        data: (s) => Column(
          children: [
            if (s.mergePending)
              MaterialBanner(
                content: const Text(
                    'Your saved products on this device could not be uploaded yet.'),
                actions: [
                  TextButton(
                    onPressed: () => ref.read(favouritesProvider.notifier).retry(),
                    child: const Text('Retry'),
                  ),
                ],
              ),
            Expanded(
              child: ListView(
                children: [
                  for (final p in s.products)
                    ListTile(
                      key: ValueKey('favourite-${p.id}'),
                      title: Text(p.name),
                      subtitle: Text(p.category),
                      onTap: () => context.push('/product/${p.id}'),
                      trailing: FavouriteToggle(product: p),
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
