using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using System;
using System.IO;
using System.Text.Json;
using IntelligentApiCS;

namespace TorusApiAgent
{
    public class GetInput
    {
        public string Address_ { get; set; }
        public string Filter_ { get; set; }
        public bool Direct_ { get; set; }
    }

    public class UploadRequest
    {
        public string FileName { get; set; }
        public IFormFile File { get; set; }
    }

    public class Startup
    {
        public void ConfigureServices(IServiceCollection services)
        {
            services.AddControllers();
        }

        public void Configure(IApplicationBuilder app, IWebHostEnvironment env)
        {
            if (env.IsDevelopment())
            {
                app.UseDeveloperExceptionPage();
            }

            app.UseRouting();

            app.UseEndpoints(endpoints =>
            {
                endpoints.MapControllers();
            });

            // Initialize TORUS API
            var appId = new Guid("7E9F8316-EA2B-41C5-AF4F-EE3E0DB1CF06");
            Api.Initialize(appId, "TorusApiAgent");
        }
    }

    [ApiController]
    [Route("api/[controller]")]
    public class TorusController : ControllerBase
    {
        [HttpGet("int")]
        public IActionResult GetInt([FromQuery] GetInput input)
        {
            var item = new Item();
            Api.getData(input.Address_, input.Filter_, out item, input.Direct_);
            int value = item != null ? item.GetValueInt("value") : -1;
            return Ok(new { value });
        }

        [HttpGet("string")]
        public IActionResult GetString([FromQuery] GetInput input)
        {
            var item = new Item();
            Api.getData(input.Address_, input.Filter_, out item, input.Direct_, 1000000);
            string value = item != null ? item.GetValueString("value") : "";
            return Ok(new { value });
        }

        [HttpPost("upload/file")]
        public IActionResult UploadFile([FromForm] IFormFile file, [FromForm] string name)
        {
            var item = new Item();
            Api.getData("data://machine/channel/currentprogram/currentfile/programnamewithpath", "machine=1&channel=1", out item, false);
            string currentPath = item != null ? item.GetValueString("value") : "";

            string ncDir = "//CNC_MEM/USER/PATH1/";
            if (!string.IsNullOrEmpty(currentPath))
            {
                int lastSlash = currentPath.LastIndexOf('/') + 1;
                ncDir = currentPath.Substring(0, lastSlash);
            }

            string tempDir = Path.GetTempPath();
            string destPath = Path.Combine(tempDir, name);

            if (!System.IO.File.Exists(destPath))
            {
                using (var stream = new StreamReader(file.OpenReadStream()))
                {
                    var content = stream.ReadToEnd();
                    var fullContent = $"%\n{name}\n{content}";
                    System.IO.File.WriteAllText(destPath, fullContent);
                }
            }

            int result = Api.UploadFile(destPath, ncDir, 1, 1, 100000000);
            return Ok(new { result });
        }
    }

    public class Program
    {
        public static void Main(string[] args)
        {
            CreateHostBuilder(args).Build().Run();
        }

        public static IHostBuilder CreateHostBuilder(string[] args) =>
            Host.CreateDefaultBuilder(args)
                .ConfigureWebHostDefaults(webBuilder =>
                {
                    webBuilder.UseStartup<Startup>();
                });
    }
}
