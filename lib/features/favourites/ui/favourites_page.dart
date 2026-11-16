import 'package:flutter/material.dart';
import '../../../core/legacy_palette.dart';
import '../../../core/widgets/section_title.dart';
import '../../catalogue/data/product.dart';
import '../../favourites/state/favourites_store.dart';
import '../../catalogue/ui/product_tile.dart';

class FavoritesPage extends StatelessWidget {
  const FavoritesPage({
    super.key,
    required this.products,
    required this.favorites,
    required this.onProductTap,
    required this.onShop,
  });
  final Future<List<Product>> products;
  final FavoritesStore favorites;
  final ValueChanged<Product> onProductTap;
  final VoidCallback onShop;

  @override
  Widget build(BuildContext context) => AnimatedBuilder(
        animation: favorites,
        builder: (context, child) => bounded(
          FutureBuilder<List<Product>>(
            future: products,
            builder: (context, snapshot) {
              final saved = (snapshot.data ?? [])
                  .where((product) => favorites.contains(product.id))
                  .toList();
              return ListView(
                padding: const EdgeInsets.fromLTRB(18, 14, 18, 30),
                children: [
                  const SectionTitle('Your favourites'),
                  const SizedBox(height: 7),
                  const Text('Saved on this device for easy browsing. Your Sagemaker Shop account is separate.', style: TextStyle(color: Colors.black54, height: 1.5)),
                  const SizedBox(height: 20),
                  if (!snapshot.hasData && !snapshot.hasError)
                    const Center(child: CircularProgressIndicator()),
                  if (snapshot.hasError)
                    const Text('Could not load saved products.'),
                  if (snapshot.hasData && saved.isEmpty)
                    Card(
                      child: Padding(
                        padding: const EdgeInsets.all(24),
                        child: Column(
                          children: [
                            const Icon(Icons.favorite_border, color: forest, size: 48),
                            const SizedBox(height: 12),
                            const Text('No favourites yet', style: TextStyle(fontWeight: FontWeight.w800, fontSize: 18, color: deep)),
                            const SizedBox(height: 8),
                            const Text('Tap the heart on any product to save it here.', textAlign: TextAlign.center),
                            const SizedBox(height: 12),
                            FilledButton(onPressed: onShop, child: const Text('Explore products')),
                          ],
                        ),
                      ),
                    ),
                  if (snapshot.hasData && saved.isNotEmpty)
                    LayoutBuilder(
                      builder: (context, constraints) {
                        final width = constraints.maxWidth;
                        final count = width < 530 ? 2 : width < 850 ? 3 : 4;
                        return GridView.builder(
                          shrinkWrap: true,
                          physics: const NeverScrollableScrollPhysics(),
                          itemCount: saved.length,
                          gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                            crossAxisCount: count,
                            mainAxisExtent: 265,
                            crossAxisSpacing: 12,
                            mainAxisSpacing: 12,
                          ),
                          itemBuilder: (context, index) => ProductTile(
                            product: saved[index],
                            favorites: favorites,
                            onTap: () => onProductTap(saved[index]),
                          ),
                        );
                      },
                    ),
                ],
              );
            },
          ),
        ),
      );
}

