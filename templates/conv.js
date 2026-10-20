(function(){var el=document.getElementById('cv-data');if(!el)return;var D=JSON.parse(el.textContent),f=document.getElementById('conv'),
amt=document.getElementById('cv-amt'),ccy=document.getElementById('cv-ccy'),dir=document.getElementById('cv-dir'),bas=document.getElementById('cv-basis'),
out=document.getElementById('cv-out'),note=document.getElementById('cv-note'),loc=f.getAttribute('data-locale')||'en';
function nf(v,d){return new Intl.NumberFormat(loc,{minimumFractionDigits:d,maximumFractionDigits:d}).format(v)}
function rf(r){return nf(r,r>=100?2:4)}
function pick(){var c=D.ccy[ccy.value],b=bas.value,r=null,lab='',st='',k;
if(b.indexOf('bot_')===0){k=b.slice(4);r=c.bot[k];lab=D.l[b];st=D.l.bot_as_of.replace('{date}',c.bot.date_fmt)}
else if(b==='mid'){if(c.mid){r=c.mid.rate;lab=D.l.mid;st=D.l.bot_as_of.replace('{date}',c.mid.date_fmt)}}
else{var bk=c.banks&&c.banks[b.slice(5)];if(bk){r=dir.value==='f2t'?bk.buying:bk.selling;lab=D.bank_names[b.slice(5)]+' '+(dir.value==='f2t'?D.l.buying:D.l.selling).toLowerCase();st=D.l.checked.replace('{when}',bk.when)}}
return{r:r,lab:lab,st:st}}
function run(){var a=parseFloat(amt.value),p=pick(),cur=ccy.value;
if(p.r==null){out.textContent=D.l.unavailable;note.textContent='';return}
if(!(a>=0)){out.textContent='';note.textContent='';return}
var t2=dir.value==='f2t';var res=t2?a*p.r:a/p.r;
out.textContent=t2?nf(a,2)+' '+cur+' = '+nf(res,2)+' TZS':nf(a,2)+' TZS = '+nf(res,2)+' '+cur;
note.textContent=D.l.rate_used.replace('{rate}',rf(p.r)).replace('{label}',p.lab)+' · '+p.st}
var q=/[?&]c=([A-Za-z]{3})/.exec(location.search);if(q&&D.ccy[q[1].toUpperCase()])ccy.value=q[1].toUpperCase();
var b=/[?&]basis=([a-z_:]+)/.exec(location.search);if(b){try{bas.value=b[1]}catch(e){}}
[amt,ccy,dir,bas].forEach(function(x){x.addEventListener('input',run);x.addEventListener('change',run)});run()})();
