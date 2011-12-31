var app = require('http').createServer(handler)
  , io = require('socket.io').listen(app)

var width,height;

app.listen(1337);

function handler(req,res){
}


io.sockets.on('connection', function (socket) {

  socket.on('size', function(data) {
    width=data[0];
    height=data[1];
  });
  socket.on('line', function(data) {
    //io.sockets.emit( 'line', [width-data[0], height-data[1], width-data[2], height-data[3]] );
    io.sockets.emit( 'line', data );
  });

});
