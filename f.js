
var f_names;

f_names=["sin","cos","tan","cot","circle","linear","spiral","exponential","quadratic","toposine",
         "invProportional","nike","sign","lemniscate","logarithm","power"];

var x = [], y = []; 
var T=4,B=-4,L=-4,R=4;
var j=0;
	

var f_display;

function plot_parac_conf(f_name)
{

	
	var fn = f_name;

	switch(fn)
		{
			case "sin":

				f_display = "正弦函数~y=\\sin x"

				j=0;
				for(i=L;i<R;i+=0.05)
				{
					x[j]=i;
					y[j]=Math.sin(i);
					if(y[j]>T+1) y[j]= null;
					if(y[j]<B-1) y[j]= null;
					j++;
					
				}
				break;

			case "cos":

				f_display = "余弦函数~y=\\cos x"

				j=0;
				for(i=L;i<R;i+=0.05)
				{
					x[j]=i;
					y[j]=Math.cos(i);
					if(y[j]>T+1) y[j]= null;
					if(y[j]<B-1) y[j]= null;
					j++;
					
				}
				break;

			case "tan":

				f_display = "正切函数~y=\\tan x"

				j=0;
				for(i=L;i<R;i+=0.05)
				{
					x[j]=i;
					y[j]=Math.tan(i);
					if(y[j]>T+1) y[j]= null;
					if(y[j]<B-1) y[j]= null;
					j++;
					
				}
				break;

			case "cot":

				f_display = "余切函数~y=\\cot x"

				j=0;
				for(i=L;i<R;i+=0.05)
				{
					x[j]=i;
					y[j]=1/Math.tan(i);
					if(y[j]>T+1) y[j]= null;
					if(y[j]<B-1) y[j]= null;
					j++;
					
				}
				break;
				
			case "circle":

				f_display = "圆方程~x^2+y^2=1"

				j=0;
				for(i=L;i<R;i+=0.05)
				{
					x[j]=Math.cos(i);
					y[j]=Math.sin(i);
					if(y[j]>T+1) y[j]= null;
					if(y[j]<B-1) y[j]= null;
					j++;
					
				}
				break;

			case "linear":

				f_display = "线性函数 ~y=x"

				j=0;
				for(i=L;i<R;i+=0.05)
				{
					x[j]=i;
					y[j]=i;
					if(y[j]>T+1) y[j]= null;
					if(y[j]<B-1) y[j]= null;
					j++;
					
				}
				break;

			case "spiral":   //阿基米德螺线

				f_display = "阿基米德螺线~ \\begin{cases}x=\\theta\\cos\\theta\\\\ y=\\theta\\sin\\theta\\end{cases}"

				j=0;
				for(i=L;i<R;i+=0.05)
				{
					k=i-L;
					x[j]=k*Math.cos(k);
					y[j]=k*Math.sin(k);
					if(y[j]>T+1) y[j]= null;
					if(y[j]<B-1) y[j]= null;

					j++;
					
				}
				break;

			case "linear":

				f_display = "线性函数 ~y=x"

				j=0;
				for(i=L;i<R;i+=0.05)
				{
					x[j]=i;
					y[j]=i;
					if(y[j]>T+1) y[j]= null;
					if(y[j]<B-1) y[j]= null;
					j++;
					
				}
				break;

			case "exponential":

				f_display = "指数函数 ~y=e^x"

				j=0;
				for(i=L;i<R;i+=0.05)
				{
					x[j]=i;
					y[j]=Math.exp(i);
					if(y[j]>T+1) y[j]= null;
					if(y[j]<B-1) y[j]= null;
					j++;
					
				}
				break;


			case "quadratic":

				f_display = "二次函数 ~y=x^2"

				j=0;
				for(i=L;i<R;i+=0.05)
				{
					x[j]=i;
					y[j]=i*i;
					if(y[j]>T+1) y[j]= null;
					if(y[j]<B-1) y[j]= null;
					j++;
					
				}
				break;

			case "toposine": //拓扑学家正弦曲线

				f_display = "拓扑学家正弦曲线 ~y=\\sin\\frac{1}{x}"

				j=0;
				for(i=L;i<R;i+=0.01) //这里把步长设置0.01，而不是通常的0.05
				{
					x[j]=i;
					y[j]=Math.sin(1/i);
					if(y[j]>T+1) y[j]= null;
					if(y[j]<B-1) y[j]= null;
					j++;
					
				}
				break;

				case "invProportional": 

				f_display = "反比例函数 ~y=\\frac{1}{x}"

				j=0;
				for(i=L;i<R;i+=0.05) 
				{
					x[j]=i;
					y[j]=1/i;
					if(y[j]>T+1) y[j]= null;
					if(y[j]<B-1) y[j]= null;
					j++;
					
				}
				break;
				
				case "nike": 

				f_display = "耐克函数 ~y=x+\\frac{1}{x}"

				j=0;
				for(i=L;i<R;i+=0.05) 
				{
					x[j]=i;
					y[j]=i+1/i;
					if(y[j]>T+1) y[j]= null;
					if(y[j]<B-1) y[j]= null;
					j++;
					
				}
				break;
				
				case "sign": 

				f_display = "符号函数 ~y=\\text{sgn} x"

				j=0;
				for(i=L;i<R;i+=0.05) 
				{
					x[j]=i;
					if(x[j]<0)y[j]=-1;
					if(x[j]>0)y[j]=1;
					
					if(Math.abs(x[j])<1/1000)
					{
						y[j]=0;
					}
					
					if(y[j]>T+1) y[j]= null;
					if(y[j]<B-1) y[j]= null;
					j++;
					
				}
				
				j=0;
				for(i=L;i<R;i+=0.01)
				{
					if(y[j]!=0&&y[j+1]==0)y[j]=null;
					if(y[j]==0&&y[j+1]!=0)y[j+1]=null;
					j++;
				}
				
				
				break;
				
				case "lemniscate": 

				f_display = "双纽线 ~(x^2+y^2)^2=2(x^2-y^2)";
				
				


				j=0;
				for(i=L;i<R;i+=0.005) //这里把步长设置0.005，而不是通常的0.05
				{
					if(Math.cos(2*i)>=0){
					x[j]=Math.cos(i)*Math.sqrt(Math.cos(2*i));
					y[j]=Math.sin(i)*Math.sqrt(Math.cos(2*i));
					}
					
					else{
						x[j]=null;
					    y[j]=null;
					}
					
					
					
					if(y[j]>T+1) y[j]= null;
					if(y[j]<B-1) y[j]= null;
					j++;
					
				}
				break;
				
				case "logarithm": 
				
				f_display = "对数函数 ~y=\\ln x"

				j=0;
				for(i=L;i<R;i+=0.05) 
				{
					x[j]=i;
					y[j]=Math.log(i);
					if(y[j]>T+1) y[j]= null;
					if(y[j]<B-1) y[j]= null;
					j++;
					
				}
				break;
				
				case "power": 
				
				f_display = "开方函数 ~y=\\sqrt{x} "

				j=0;
				for(i=L;i<R;i+=0.005) 
				{
					x[j]=i;
					y[j]=Math.sqrt(i);
					if(y[j]>T+1) y[j]= null;
					if(y[j]<B-1) y[j]= null;
					j++;
					
				}
				break;
				
			

			default:
				f_display = "y = x"

				j=0;
				for(i=L;i<R;i+=0.05)
				{
					x[j]=i;
					y[j]=i;
					if(y[j]>T+1) y[j]= null;
					if(y[j]<B-1) y[j]= null;
					j++;
					
				}
				break;
		}
	}