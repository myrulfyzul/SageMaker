import 'package:flutter/material.dart';
import '../../../core/widgets/section_title.dart';
import '../../catalogue/data/product.dart';
import '../../favourites/state/favourites_store.dart';
import '../../catalogue/ui/product_tile.dart';

class ShopPage extends StatefulWidget {
  const ShopPage({
    super.key,
    required this.products,
    required this.favorites,
    required this.onProductTap,
    required this.onCart,
  });
  final Future<List<Product>> products;
  final FavoritesStore favorites;
  final ValueChanged<Product> onProductTap;
  final VoidCallback onCart;
  @override
  State<ShopPage> createState() => _ShopPageState();
}

class _ShopPageState extends State<ShopPage> {
  String search = '';
  String category = 'All';

  @override
  Widget build(BuildContext context) => bounded(
        FutureBuilder<List<Product>>(
          future: widget.products,
          builder: (context, snapshot) {
            final all = snapshot.data ?? [];
            final categories = ['All', ...all.map((p) => p.category).toSet()];
            final filtered = all.where((p) =>
                (category == 'All' || p.category == category) &&
                ('${p.name} ${p.description}'.toLowerCase().contains(search.toLowerCase()))).toList();
            return ListView(
              padding: const EdgeInsets.fromLTRB(18, 12, 18, 28),
              children: [
                const SectionTitle('Explore the shop'),
                const SizedBox(height: 5),
                const Text('DEMO catalogue and sample prices. Not connected to Sagemaker’s real inventory.', style: TextStyle(color: Colors.black54, height: 1.4)),
                const SizedBox(height: 17),
                TextField(
                  onChanged: (value) => setState(() => search = value),
                  decoration: InputDecoration(
                    hintText: 'Search products',
                    prefixIcon: const Icon(Icons.search),
                    filled: true,
                    fillColor: Colors.white,
                    border: OutlineInputBorder(borderRadius: BorderRadius.circular(14), borderSide: BorderSide.none),
                  ),
                ),
                const SizedBox(height: 12),
                SingleChildScrollView(
                  scrollDirection: Axis.horizontal,
                  child: Row(children: categories.map((item) => Padding(
                    padding: const EdgeInsets.only(right: 8),
                    child: ChoiceChip(
                      label: Text(item),
                      selected: category == item,
                      onSelected: (_) => setState(() => category = item),
                      selectedColor: const Color(0xFFDBE9E2),
                    ),
                  )).toList()),
                ),
                const SizedBox(height: 16),
                if (snapshot.hasError) const Text('Could not load products.'),
                if (!snapshot.hasData && !snapshot.hasError) const Center(child: Padding(padding: EdgeInsets.all(28), child: CircularProgressIndicator())),
                if (snapshot.hasData && filtered.isEmpty) const Padding(padding: EdgeInsets.all(16), child: Text('No matching items. Try a different search.')),
                if (snapshot.hasData && filtered.isNotEmpty)
                  LayoutBuilder(builder: (context, constraints) {
                    final width = constraints.maxWidth;
                    final count = width < 530 ? 2 : width < 850 ? 3 : 4;
                    return GridView.builder(
                      shrinkWrap: true,
                      physics: const NeverScrollableScrollPhysics(),
                      itemCount: filtered.length,
                      gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                        crossAxisCount: count,
                        mainAxisExtent: 265,
                        crossAxisSpacing: 12,
                        mainAxisSpacing: 12,
                      ),
                      itemBuilder: (context, index) => ProductTile(
                        product: filtered[index],
                        favorites: widget.favorites,
                        onTap: () => widget.onProductTap(filtered[index]),
                      ),
                    );
                  }),
                const SizedBox(height: 20),
                OutlinedButton.icon(
                  onPressed: widget.onCart,
                  icon: const Icon(Icons.shopping_cart_outlined),
                  label: const Text('View in-app shopping cart'),
                ),
              ],
            );
          },
        ),
      );
}

