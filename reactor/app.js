var app = require('http').createServer()
  , io = require('socket.io').listen(app)

var pg = require('pg');

io.settings["log level"] = 1;
console.log( io );

pg.defaults.database = 'operator';
pg.defaults.password = 'password';

var client = new pg.Client();
client.connect();

var width,height;

app.listen(1337);

io.sockets.on('connection', function (socket) {
  

  socket.on('map', function(data) {
    console.log( data );
    var ll=data[0],bb=data[1],rr=data[2],tt=data[3];

    var last_shape_id=null;

    qs = "SELECT * FROM shapes WHERE (shape_pt_lat BETWEEN $1 AND $2) AND (shape_pt_lon BETWEEN $3 AND $4) ORDER BY shape_id, shape_pt_sequence";
    qs = "SELECT * FROM shapes";
    var query = client.query( qs );//, [bb,tt,ll,rr] );
    query.on( 'row', function(row){
      if(row.shape_id!=last_shape_id) {
        socket.emit( 'newshape', row.shape_id );
        console.log( "new shape id "+row.shape_id );
      } else {
        socket.emit( 'pt', [Math.round(parseFloat(row.shape_pt_lon)*10000), 
                            Math.round(parseFloat(row.shape_pt_lat)*10000)] );
      }

      last_shape_id = row.shape_id;
    });
  });

});

