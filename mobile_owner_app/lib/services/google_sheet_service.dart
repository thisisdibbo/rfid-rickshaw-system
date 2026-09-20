import 'dart:convert';

import 'package:firebase_database/firebase_database.dart';
import 'package:http/http.dart' as http;



class GoogleSheetService {


  GoogleSheetService({
    FirebaseDatabase? database,
  }) : _db = database ?? FirebaseDatabase.instance;



  final FirebaseDatabase _db;



  String _apiUrl = "";



  String get apiUrl => _apiUrl;




  Future<void> initialize() async {


    try {


      final snapshot =
      await _db
          .ref(
        "settings/google_sheet/api_url",
      )
          .get();



      _apiUrl =
          snapshot.value?.toString() ?? "";



      print(
          "[GOOGLE INITIAL URL] $_apiUrl"
      );




      _db
          .ref(
        "settings/google_sheet/api_url",
      )
          .onValue
          .listen(


            (event){


          _apiUrl =
              event.snapshot.value?.toString() ?? "";



          print(
              "[GOOGLE URL UPDATED] $_apiUrl"
          );


        },


        onError: (error){


          print(
              "[GOOGLE URL LISTENER ERROR] $error"
          );


        },


      );



    }


    catch(e){


      print(
          "[GOOGLE URL INIT ERROR] $e"
      );


    }


  }







  Future<bool> sendSession(
      Map<String,dynamic> data
      ) async {



    if(_apiUrl.isEmpty){


      print(
          "[GOOGLE] URL EMPTY"
      );


      return false;


    }




    try {



      print(
          "=============================="
      );


      print(
          "[GOOGLE PAYLOAD]"
      );


      print(
          jsonEncode(data)
      );



      print(
          "=============================="
      );





      final response =
      await http.post(



        Uri.parse(_apiUrl),



        headers: {


          "Content-Type":
          "application/json"



        },



        body:
        jsonEncode(data),



      );





      print(
          "[GOOGLE RESPONSE] ${response.statusCode}"
      );



      print(
          response.body
      );



      return response.statusCode == 200;




    }



    catch(e){



      print(
          "[GOOGLE MOBILE ERROR] $e"
      );



      return false;



    }



  }





}






// USE THIS EVERYWHERE
final googleSheetService =
GoogleSheetService();