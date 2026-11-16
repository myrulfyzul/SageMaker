import 'package:flutter/material.dart';
import '../../../core/legacy_palette.dart';
import '../../catalogue/data/product.dart';
import '../../favourites/state/favourites_store.dart';

// Reusable heart: updates all tiles and details immediately.
class FavoriteButton extends StatelessWidget {
  const FavoriteButton({super.key, required this.product, required this.favorites});
  final Product product;
  final FavoritesStore favorites;

  @override
  Widget build(BuildContext context) => AnimatedBuilder(
        animation: favorites,
        builder: (context, child) {
          final saved = favorites.contains(product.id);
          return Material(
            color: Colors.white,
            borderRadius: BorderRadius.circular(40),
            child: IconButton(
              tooltip: saved ? 'Remove from favourites' : 'Save to favourites',
              icon: Icon(saved ? Icons.favorite : Icons.favorite_border,
                  color: saved ? const Color(0xFFB64B58) : forest),
              onPressed: () {
                favorites.toggle(product.id);
              },
            ),
          );
        },
      );
}

