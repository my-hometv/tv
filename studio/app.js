const file=document.getElementById("playlistFile");
const channelsDiv=document.getElementById("channels");

let channels=[];

file.addEventListener("change",loadPlaylist);

function loadPlaylist(e){

    const reader=new FileReader();

    reader.onload=function(){

        parseM3U(reader.result);

    }

    reader.readAsText(e.target.files[0]);

}

function parseM3U(text){

    channels=[];

    const lines=text.split("\n");

    let current="";

    lines.forEach(line=>{

        line=line.trim();

        if(line.startsWith("#EXTINF")){

            current=line.split(",").pop();

        }

        else if(line.startsWith("http")){

            channels.push({

                name:current,

                url:line

            });

        }

    });

    render();

}

function render(){

    document.getElementById("channelCount").innerText="Channels: "+channels.length;

    channelsDiv.innerHTML="";

    channels.forEach(c=>{

        channelsDiv.innerHTML+=`

        <div class="channel">

            <b>${c.name}</b><br>

            <small>${c.url}</small>

        </div>

        `;

    });

}
