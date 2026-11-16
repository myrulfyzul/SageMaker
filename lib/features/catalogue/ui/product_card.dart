import 'package:flutter/material.dart';

import '../../../app/theme.dart';
import '../../../core/money.dart';
import '../../../core/widgets/ui_kit.dart';
import '../../favourites/ui/favourites_screen.dart';
import '../data/catalogue_models.dart';
import '../data/product.dart';

/// Product image with a branded placeholder while loading or on error.
class ProductImageView extends StatelessWidget {
  const ProductImageView({super.key, required this.product});
  final CatalogueProduct product;

  @override
  Widget build(BuildContext context) {
    final url = product.firstImage;
    const placeholder = DecoratedBox(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(0xFFF3EEE4), Color(0xFFE8F0EB)],
        ),
      ),
      child: Center(
          child:
              Icon(Icons.shopping_bag_outlined, size: 38, color: kSecondary)),
    );
    if (url == null) return placeholder;
    return Image.network(
      url,
      fit: BoxFit.cover,
      errorBuilder: (_, __, ___) => placeholder,
      frameBuilder: (_, child, frame, sync) => sync
          ? child
          : AnimatedOpacity(
              opacity: frame == null ? 0 : 1,
              duration: const Duration(milliseconds: 350),
              child: frame == null ? placeholder : child,
            ),
    );
  }
}

/// The favourites feature works with the lighter [Product]; this converts.
extension CatalogueProductFavourite on CatalogueProduct {
  Product toFavouriteProduct() => Product(
        id: id,
        name: name,
        category: category.name,
        description: description,
        imageUrl: firstImage ?? '',
        productUrl: '',
        priceSen: priceSen,
      );
}

class ProductCard extends StatelessWidget {
  const ProductCard({super.key, required this.product, required this.onTap});
  final CatalogueProduct product;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Stack(children: [
      Positioned.fill(
          child: PressableScale(onTap: onTap, child: _card(context))),
      Positioned(
        right: 8,
        top: 8,
        child: Material(
          color: Colors.white.withValues(alpha: 0.92),
          shape: const CircleBorder(),
          elevation: 2,
          shadowColor: Colors.black26,
          child: FavouriteToggle(product: product.toFavouriteProduct()),
        ),
      ),
    ]);
  }

  Widget _card(BuildContext context) {
    final theme = Theme.of(context);
    final stockColor = product.stockText.startsWith('Out')
        ? kError
        : product.stockText.startsWith('Low')
            ? const Color(0xFFB7791F)
            : kSuccess;
    return Container(
      decoration: BoxDecoration(
        color: kCard,
        borderRadius: BorderRadius.circular(kRadiusLarge),
        boxShadow: softShadow(),
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Expanded(
            child: Stack(fit: StackFit.expand, children: [
              ProductImageView(product: product),
              const Positioned(
                left: 0,
                right: 0,
                bottom: 0,
                height: 50,
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      begin: Alignment.topCenter,
                      end: Alignment.bottomCenter,
                      colors: [Colors.transparent, Color(0x33000000)],
                    ),
                  ),
                ),
              ),
            ]),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 10, 12, 12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(product.category.name.toUpperCase(),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: theme.textTheme.labelSmall),
                const SizedBox(height: 3),
                Text(product.name,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: theme.textTheme.titleSmall?.copyWith(height: 1.25)),
                const SizedBox(height: 6),
                Row(children: [
                  Text(formatRm(product.priceSen),
                      style: const TextStyle(
                          color: kPrimary,
                          fontWeight: FontWeight.w800,
                          fontSize: 15)),
                  const Spacer(),
                  Container(
                    width: 8,
                    height: 8,
                    decoration: BoxDecoration(
                        color: stockColor, shape: BoxShape.circle),
                  ),
                ]),
                const SizedBox(height: 2),
                Text(product.stockText,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: theme.textTheme.bodySmall),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
