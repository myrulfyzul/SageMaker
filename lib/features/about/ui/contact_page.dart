import 'package:flutter/material.dart';
import '../../../core/legacy_palette.dart';
import '../../../core/widgets/section_title.dart';

class ContactPage extends StatelessWidget {
  const ContactPage({super.key});
  @override
  Widget build(BuildContext context) => bounded(ListView(
    padding: const EdgeInsets.fromLTRB(18, 14, 18, 32),
    children: const [
      SectionTitle('Contact & support'),
      SizedBox(height: 14),
      Card(child: Padding(padding: EdgeInsets.all(22), child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(Icons.support_agent, color: forest, size: 34),
          SizedBox(height: 12),
          Text('Demo support information', style: TextStyle(fontWeight: FontWeight.w800, fontSize: 18)),
          SizedBox(height: 8),
          Text('This app does not send messages or orders to Sagemaker. For real product, shipping, returns or payment enquiries, contact the official company through its own channels.'),
          SizedBox(height: 10),
          Text('Your demo orders appear under Orders and can be tracked here in the app.', style: TextStyle(color: Colors.black54)),
        ],
      ))),
    ],
  ));
}

