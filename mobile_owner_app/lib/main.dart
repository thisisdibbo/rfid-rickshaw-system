import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_database/firebase_database.dart';
import 'package:flutter/material.dart';

import 'app.dart';
import 'firebase_options.dart';
import 'services/google_sheet_service.dart';



Future<void> main() async {

  WidgetsFlutterBinding.ensureInitialized();



  await Firebase.initializeApp(
    options:
    DefaultFirebaseOptions.currentPlatform,
  );



  // Firebase offline support
  FirebaseDatabase.instance
      .setPersistenceCacheSizeBytes(
    20 * 1024 * 1024,
  );


  FirebaseDatabase.instance
      .setPersistenceEnabled(true);



  // Start Google Sheet URL listener
  //
  // Desktop changes:
  // settings/google_sheet/api_url
  //
  // Mobile receives automatically.

  try {

    await googleSheetService.initialize();

  }
  catch(e){

    print(
        "[GOOGLE SHEET INIT ERROR] $e"
    );

  }



  runApp(
    RickshawOwnerApp(),
  );

}