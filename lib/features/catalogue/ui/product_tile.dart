import 'package:flutter/material.dart';
import '../../../core/legacy_palette.dart';
import '../../../core/money.dart';
import '../../catalogue/data/product.dart';
import '../../favourites/state/favourites_store.dart';
import '../../favourites/ui/favorite_button.dart';

class ProductTile extends StatelessWidget {
  const ProductTile({
    super.key,
    required this.product,
    required this.favorites,
    required this.onTap,
    this.compact = false,
  });
  final Product product;
  final FavoritesStore favorites;
  final VoidCallback onTap;
  final bool compact;

  @override
  Widget build(BuildContext context) => Card(
        margin: EdgeInsets.zero,
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onTap,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Expanded(
                child: Stack(
                  fit: StackFit.expand,
                  children: [
                    ProductImage(product: product),
                    Positioned(
                      right: 7,
                      top: 7,
                      child: FavoriteButton(product: product, favorites: favorites),
                    ),
                  ],
                ),
              ),
              Padding(
                padding: const EdgeInsets.all(11),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(product.category.toUpperCase(), style: const TextStyle(fontSize: 9, color: forest, fontWeight: FontWeight.w800, letterSpacing: 1)),
                    const SizedBox(height: 3),
                    Text(product.name, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w700, color: deep), maxLines: 2, overflow: TextOverflow.ellipsis),
                    const SizedBox(height: 6),
                    Text('${formatRm(product.priceSen)} • DEMO', style: const TextStyle(fontSize: 12, color: deep, fontWeight: FontWeight.w800)),
                    const SizedBox(height: 4),
                    Row(children: [
                      Text(compact ? 'Details' : 'View details', style: const TextStyle(color: forest, fontSize: 11, fontWeight: FontWeight.w700)),
                      const SizedBox(width: 4),
                      const Icon(Icons.arrow_forward, size: 13, color: forest),
                    ]),
                  ],
                ),
              ),
            ],
          ),
        ),
      );
}

class ProductImage extends StatelessWidget {
  const ProductImage({super.key, required this.product});
  final Product product;
  @override
  Widget build(BuildContext context) => Image.network(
        product.imageUrl,
        fit: BoxFit.cover,
        errorBuilder: (context, error, stackTrace) => const ColoredBox(
          color: Color(0xFFECEDE5),
          child: Center(child: Icon(Icons.shopping_bag_outlined, color: forest, size: 38)),
        ),
      );
}

